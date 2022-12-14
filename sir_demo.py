import argparse
from datetime import datetime
import time
import csv

import pandas as pd
import numpy as np

import torch
import torch.nn as nn

from scipy.integrate import odeint

import occamnet.Bases as Bases
from occamnet.Losses import CrossEntropyLoss
from occamnet.Network import NetworkConstants
from occamnet.SparseSetters import SetNoSparse as SNS


parser = argparse.ArgumentParser()
parser.add_argument("--target_var", choices={"s", "i", "r"}, default='s', 
                    help="Target data to be fitted (one of 's', 'i', or 'r')")
args = parser.parse_args()


def model(y,t):
    s,i,r = y
    dydt = [-0.5*s*i, 0.5*s*i-0.2*i, 0.2*i]
    return dydt

if __name__ == '__main__':

    ################ Generate data ################

    X0 = [1, 0.001, 0] # initial conditions

    t = np.arange(60) # time points

    # solve ODE
    X = odeint(model,X0,t)
    Y = torch.tensor(np.diff(X[1:, ], axis=0) - 0.5*np.diff(np.diff(X, axis=0), axis=0), 
                    dtype=torch.float)
    X = torch.tensor(X[1:-1, [0,1]], dtype=torch.float) # Use s and i as input variables

    if args.target_var == 's':
        Y = Y[:, [0]] # Fit only s
    elif args.target_var == 'i':
        Y = Y[:, [1]] # Fit only i
    else:
        Y = Y[:, [2]] # Fit only i
    
    inputSize = 2 # Number of input variables in each individual dataset
    outputSize = 1 # Number of output variables in each individual dataset

    ################ Initialize OccamNet ################

    ensembleMode = False # Toggle ensemble learning

    # Default hyperparameters
    epochs = 1000
    batchesPerEpoch = 1
    learningRate = 1
    constantLearningRate = 0.05
    decay = 1
    temp = 10
    endTemp = 10
    sampleSize = 100 # Number of functions to sample

    # Regularization parameters
    activationWeight = 0
    constantWeight = 0

    # Sweep parameters
    sDev_sweep = [5]
    top_sweep = [1]
    equalization_sweep = [5]

    # Activation layers
    layers = [
        [Bases.Add(), Bases.Subtract(), Bases.Multiply(),  Bases.Divide(), Bases.AddConstant(), Bases.MultiplyConstant()],
        [Bases.Add(), Bases.Subtract(), Bases.Multiply(), Bases.Divide(), Bases.AddConstant(), Bases.MultiplyConstant()],
        [Bases.Add(), Bases.Subtract(), Bases.Multiply(), Bases.Divide(), Bases.AddConstant(), Bases.MultiplyConstant()]
    ]

    
    ################ Training ################

    file_name = "SIRDemo_" + args.target_var
    date_time = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")[:-3] 
    file_path = 'results/' + file_name + '_' + date_time + ".csv"

    with open(file_path, 'w') as f:
        writer = csv.writer(f)

        header = ['mse', 'expression', 'sDev', 'top', 'equalization', 'runtime']

        writer.writerow(header)

    for sDev in sDev_sweep:
        for top in top_sweep:
            for equalization in equalization_sweep:

                print('Training with parameters: sDev={sDev}, top={top}, equalization={eq}'.format(
                    sDev=sDev, 
                    top=top,
                    eq=equalization))

                start = time.time()

                loss = CrossEntropyLoss(sDev, 
                                        top, 
                                        anomWeight=0, 
                                        constantWeight=constantWeight, 
                                        activationWeight=activationWeight)

                sparsifier = SNS()

                n = NetworkConstants(inputSize, 
                                    layers, 
                                    outputSize, 
                                    sparsifier, 
                                    loss, 
                                    learningRate, 
                                    constantLearningRate, 
                                    temp, 
                                    endTemp, 
                                    equalization, 
                                    skipConnections = True)

                n.setConstants([0 for j in range(n.totalConstants)])

                train_function = n.trainFunction(epochs, 
                                                batchesPerEpoch, 
                                                sampleSize, 
                                                decay, 
                                                X, 
                                                Y, 
                                                useMultiprocessing = True, 
                                                numProcesses = 20, 
                                                ensemble=ensembleMode)

                ### Evaluation ###
            
                output = n.forwardFitConstants(train_function, X, Y, ensemble=ensembleMode)

                MSELoss = nn.MSELoss()
                train_mse = MSELoss(Y, output[:,0]).item()

                expression = str(n.applySymbolicConstant(train_function))

                end = time.time()
                minutes = (end - start)/60

                with open(file_path, 'a') as f:
                    writer = csv.writer(f)

                    data = [train_mse, expression, sDev, top, equalization, minutes]

                    writer.writerow(data)
           