

#Assume only one equlibrium state



#combine the two using null paramters for interactive mode
import os




#___________All setup for packages_____________________

import sys
import math
import warnings



try:
    import matplotlib.pyplot as plt
except:
    os.system("py -m pip install matplotlib -t .")
    import matplotlib.pyplot as plt
    
try:
    import numpy as np
except:
    os.system("py -m pip install numpy -t .")
    import numpy as np
    
try:
    import pandas as pd
except:
    os.system("py -m pip install pandas -t .")
    import pandas as pd

try:
    import scipy
except:
    os.system("py -m pip install scipy -t .")
    import scipy

#import matplotlib.pyplot as plt
#import numpy as np
#import pandas as pd


import scipy.stats
from scipy.stats import shapiro 
from scipy.stats import norm
from scipy import stats



from numpy import *
nan_policy = "reject"   # options: "reject", "drop_rows", "drop_cols", "ignore"
warn_on_nan = True


print("MDTest – a code that helps assess equilibrium for recorded time series of a thermodynamic quantity \n Jerry Wang, Haobin Wang, and Hai Lin \n University of Colorado Denver, Denver, Colorado, 2026 \n")

class Tee:
    def __init__(self, *files):
        self.files = files
    def write(self, obj):
        for f in self.files:
            try:
                f.write(obj)
            except ValueError:
                pass  # file already closed
    def flush(self):
        for f in self.files:
            try:
                f.flush()
            except ValueError:
                pass  # file already closed

def isValidNumber(number): #returns if the value a valid number
    periodCount = 0
    i = 0
    while i<len(number):
        if number[i] == ".":
            periodCount+=1 
        i+=1
    number = number.replace(".", "") #replace all periods with blank space so the isnumeric method can return true even if its a float
    if (periodCount>1) or not(number.isnumeric()): #if string has more than 1 period or has nonnumeric characters (excluding periods) then prompt user again
        return False
    return True



def calcVariance(xArray, average):
    summation = 0
    i = 0
    while i<len(xArray):
        summation += (average-xArray[i])**2
        i+=1
    
    if len(xArray)<=1:
        return np.zeros_like(summation)
    else:
        s2 = summation/(len(xArray)-1)
        return s2


    
def mannKendallTest(data,n):
    data = list(data)
    def reverseMerge(orig, comb, left, mid, rightMax):
        L = left
        r = mid
        c = left
        addInv = 0
        invAmount = mid-left
        
        while c < rightMax: 
            if L >= mid:
                comb[c] = orig[r]
                r += 1
                #add by mult by 0 not included
            elif r >= rightMax: #should just be =
                comb[c] = orig[L]
                L += 1
            elif orig[L] >= orig[r]:
                comb[c] = orig[L]
                L += 1
                invAmount += -1
            else: #orig[l]<orig[r]
                comb[c] = orig[r]
                r += 1
                addInv += invAmount
            c += 1
        return addInv
    
    def oppositeInvCount(data):
        n = len(data)
        numInversions = 0
        amountRead = 1
        combined = data.copy()
        orginal = combined.copy()
        if not isinstance(combined, list):
            combined = list(combined)
            orginal = list(orginal)

        
        while (amountRead < n):
            left = 0
            while (left + amountRead < n): 
                mid = left + amountRead
                #This code was bugged when ported from Spyder to Vscode. Fixed this way
                import builtins
                rightMax = builtins.min(left + amountRead*2, len(orginal))
                numInversions += reverseMerge(orginal, combined, left, mid, rightMax)
                left += amountRead*2
            for i in range(n):
                orginal[i] = combined[i]
            amountRead = amountRead*2
        return (numInversions)

    I = oppositeInvCount(data)
    #The following is a naive implementation which is O(n^2)
    #I = 0
    #i = 0 #loop variable
    #while i<n-1:
        #j=i+1
        #while j<n:
            #if data[j]-data[i]>0:
                #I+=1
            #j+=1
        #i+=1 
    S=I*2 -(n*(n-1)/2)
    sigma = ((n*(n-1)*(2*n+5))/18)**0.5
    uS=S/sigma
    
    return uS

    #all other paper
    #https://www.epa.gov/sites/default/files/2016-05/documents/tech_notes_6_dec2013_trend.pdf
    #S = 0
    
    # i = 0 #loop variable
    # while i<n-1:
    #     j=i+1
    #     while j<n:
    #         if data[j]-data[i]>0:
    #             #print("greater")
    #             S+=1
    #         elif data[j]-data[i]<0:
    #             #print("lesser")
    #             S+=-1
    #         else:
    #             print("equal")
    #             S+=0
    #         j+=1
    #     i+=1
    # print(S)
    # tau = S / ((n*(n-1)/2))
    # print(tau)
    
    
    ######

def vonNeunmannTest (data, n):
    q2 = 0
    k=0
    while k<n-1:
        q2 += (data[k+1]-data[k])**2
        k+=1
    q2 = q2/(2*(n-1))
    s2 = calcVariance(data, np.mean(data))
    r = q2/s2
    
    sigmar = ((1+(1/(n-1)))/(n+1))**0.5
    
    ur = (r-1)/sigmar
    return ur



def runTest(fullFileName, readGraph, titles, colRead, ts, m, n, alphaValue):
    
        
    #testing purposes
    #readGraph = np.transpose(readGraph)
    #readGraph[1] = 0.00025*readGraph[0]+readGraph[1]
    #readGraph = np.transpose(readGraph)
    ###
    
    
    initialGraph = np.transpose(readGraph)
    #plt.title("Initial Graph: Time vs " + titles[colRead]) 
    plt.title("Initial Graph: Time vs Observable") 
    if(not(len(titles)==0)):
        plt.xlabel(titles[0]) #Should be time
        plt.ylabel(titles[colRead]) 
    else:
        plt.xlabel("Time")
        plt.ylabel("Filler Title") 
    plt.plot(initialGraph[0],initialGraph[colRead])
    plt.show()
    
    
    
    
    deltaT = readGraph[1][0] - readGraph[0][0]
    
    
    
    #minimum m should be 25
    #medium should be 100
    #400 should be most powerful
    
    #m=1
    
    
    
    npt = int(len(readGraph)-(ts/deltaT))
    
    remainder = npt % m
    #n has to be greater than 24
    
    startIndex = int(ts//deltaT)
    
    #cuts the array from the time start
    cutData = readGraph[startIndex:startIndex+int((m*n))] 
    
    
    if not(remainder == 0):
        arraysOfValues = np.array_split(cutData[0 : int(len(cutData)-remainder)], n)
    else:
        arraysOfValues = np.array_split(cutData[0:], n)
        
    xkArray = []
    xKVariances= []
    
    for array in arraysOfValues:
        average=np.mean(array, axis=0)
        variances=calcVariance(array, average)
        
        xkArray.append(average)
        xKVariances.append(variances)
        
    xkCombined = np.transpose(xkArray)
    xkCombined = xkCombined.astype('float64')
    #plt.title("Time vs " + titles[colRead] + " m=" + str(m)) 
    plt.title("Time vs Observable" + " m=" + str(m)) 
    plt.xlabel(titles[0]) #Should be time
    plt.ylabel(titles[colRead]) 
    timeAxis = xkCombined[0][0:n-1]
    energyAxis = xkCombined[colRead][0:n-1]
    plt.plot(timeAxis,energyAxis)
    plt.show()
    
    xKVariances= np.transpose(xKVariances).astype('float64')
    xKDeviations = xKVariances**0.5
    output_file = "testResults.txt"
    f = open(output_file, "w")

    sys.stdout = Tee(sys.stdout, f)

    
    print("Printing Results for a test on the file: " + fullFileName)
    print("Column Read: " + str(colRead))
    print("Listed of inputted parameters:\nStart Time: " + str(ts))
    print("m-value: " + str(m))
    print("n-value: " + str(n))
    print("Testing with an alpha value of: " + str(alphaValue))
    print("__________________________________________________")

    
    
    print("\nTest a) Lack of Trend in xk (Mann-Kendall for mean):")
    testStatistic = mannKendallTest(xkCombined[colRead], len(xkCombined[colRead]))
    print("Test Statistic: " + str(testStatistic))
    pValue = scipy.stats.norm.sf(abs(testStatistic))*2
    print("P-Value: " + str(pValue))
    if pValue<=alphaValue:
        print("Test fails since P-Value of " + str(pValue) + " is less than " + str(alphaValue))
        testA = False
    else:
        print("Test passes since P-Value of " + str(pValue) + " is greater than " + str(alphaValue))
        testA = True
    
    
    
    print("\nTest b) Lack of trend in Sk (Mann-Kendall for variance):")
    testStatistic = mannKendallTest(xKDeviations[colRead], len(xKDeviations[colRead]))
    print("Test Statistic: " + str(testStatistic))
    pValue = scipy.stats.norm.sf(abs(testStatistic))*2
    print("P-Value: " + str(pValue))
    if pValue<=alphaValue:
        print("Test fails since P-Value of " + str(pValue) + " is less than " + str(alphaValue))
        testB = False
    else:
        print("Test passes since P-Value of " + str(pValue) + " is greater than " + str(alphaValue))
        testB = True
    
    
    print("\nTest c) W Test for Normality:")
    WResult = (shapiro(xkCombined[colRead]))
    print("Test Statistic: " + str(WResult[0]))
    print("P-Value: " + str(WResult[1]))
    if WResult[1]<=alphaValue:
        print("Test fails since P-Value of " + str(WResult[1]) + " is less than " + str(alphaValue))
        testC = False
    else:
        print("Test passes since P-Value of " + str(WResult[1]) + " is greater than " + str(alphaValue))
        testC = True
    
    print("\nTest d) von Neumann test for serial correlation:")
    if not(testC):
        print("*****THE FOLLOWING RESULTS ARE VOID SINCE THE NORMALITY TEST FAILED**************\n")
    testStatistic = vonNeunmannTest(xkCombined[colRead], len(xkCombined[colRead]))
    print("Test Statistic: " + str(testStatistic))
    pValue = scipy.stats.norm.sf(abs(testStatistic))*2
    print("P-Value: " + str(pValue))
    if pValue<=alphaValue:
        print("Test fails since P-Value of " + str(pValue) + " is less than " + str(alphaValue))
        testD = False
    else:
        print("Test passes since P-Value of " + str(pValue) + " is greater than " + str(alphaValue))
        testD = True
    
    results = [False]*2
    print("\n______________________________________")
    if(not(testA) or not(testB)):
        print("Recommend increasing ts (start time)")
        pass
    else:
        results[0] = True
        print("Tests a and b both passed")
        
    if(not(testC) or not(testD)):
        print("Recommend increasing time step by increasing m")
        pass
    else:
        print("Tests c and d both passed")
        results[1] = True
    
    
    if(testA and testB and testC and testD):
        print("All tests passed!\nData is most likely equilibriated.")
        print("Use the max n to increase power if that was not already done so.")
        print("The confidence interval for 97.5% of the data is: ")
        average=np.mean(xkCombined[colRead])
        variance=calcVariance(xkCombined[colRead], average)
        dev = variance**0.5
        confidenceInterval = stats.t(df=(n-1)).ppf((0.025, 0.975))
        confidenceInterval*=(dev/(n**0.5))
        confidenceInterval += [average, average]
        print(confidenceInterval)
        # restore stdout and close file
        sys.stdout = sys.__stdout__
        f.close()
        return True, results
    else:
        print("Overall test fails.")
        # restore stdout and close file
        sys.stdout = sys.__stdout__
        f.close()
        return False, results
    



def programmaticForm(file, delim, colRead, ts, m, n, alphaValue):
    
    # ---- Guard: check if file exists ----
    if not os.path.isfile(file):
        raise FileNotFoundError(f"File '{file}' was not found.")
    fileType = file[-3:len(file)]
    if fileType in ["csv"]:
        graph = pd.read_csv(file)
    elif fileType in ["dat"]:
        if delim in [" ", "space"]:
            graph = pd.read_csv(file, delim_whitespace = True)
        elif delim in ["comma", ","]:
            graph = pd.read_csv(file)
    elif fileType in ["txt"]:
        if delim in [" ", "space"]:
            graph = pd.read_csv(file, delim_whitespace = True)
        elif delim in ["comma", ","]:
            graph = pd.read_csv(file)
        
    
    #graph = pd.read_csv("TimeSeriesData.csv")
    #graph = pd.read_csv("NarK_h2p_V.dat", delim_whitespace=True)
    #graph = pd.read_csv("NarK_h2p_TM4c_RMSD.dat", delim_whitespace=True)
    
    
    # ---- NaN handling ----
    
    if graph.isna().any().any():

        if warn_on_nan:
            warnings.warn("Missing values detected in input graph.")

        if nan_policy == "reject":
            raise ValueError("Input graph contains NaN or empty values.")

        elif nan_policy == "drop_rows":
            graph = graph.dropna(axis=0)

        elif nan_policy == "drop_cols":
            graph = graph.dropna(axis=1)

    # Convert after validation
    readGraph = graph.to_numpy()
    
    
        
    #titles
    try:
        readGraph = readGraph[0:].astype('float64')
        print("No title could be read. (Continuing with rest of program)")
        titles = []
        titles.append("Time") #Assume Time is the First Column
        for i in range(len(readGraph[0, :])-1):
            titles.append("Filler Title")
    except ValueError:
        titles = readGraph[0, :]
        readGraph = readGraph[1:].astype('float64')
    
    
    
    #Checking and converting user values
    try:
        ts = float(ts)
    except ValueError:
        print("The inputted start time (ts) of \'" + ts + "\' is not valid.")
        print("Exiting program")
        sys.exit()
    try:
        m = int(m)
    except ValueError:
        print("The inputted m-value of \'" + m + "\' is not valid.")
        print("Exiting program")
        sys.exit()
    try:
        colRead = int(colRead)
    except ValueError:
        print("The inputted column read value of \'" + colRead + "\' is not valid.")
        print("Exiting program")
        sys.exit()
    try:
        alphaValue = float(alphaValue)
    except ValueError:
        print("The inputted alpha value of \'" + alphaValue + "\' is not valid.")
        print("Exiting program")
        sys.exit()
    
    
    if not (n==None):
        try:
            n = int(n)
        except ValueError:
            print("The inputted n value of \'" + n + "\' is not valid.")
            deltaT = readGraph[1][0] - readGraph[0][0]
            npt = int(len(readGraph)-(ts/deltaT))
            n = npt//m
            print("Automatically using max n-value of " + str(n) + " based off the other parameters.\n")
            
    else:
        deltaT = readGraph[1][0] - readGraph[0][0]
        npt = int(len(readGraph)-(ts/deltaT))
        n = npt//m

    if n<24:
        print("NOTE THE INPUTTED n-value OF \'" + str(n) + "\' is LESS THAN 24. THE FOLLOWING STATISTICAL RESULTS ARE INVALID DUE TO n BEING LESS THAN 24.\n")

    runTest(file, readGraph, titles, colRead, ts, m, n, alphaValue)
    
    





def autoFind(file, delim, colRead, ts, m, n, alphaValue):
    
    # ---- Guard: check if file exists ----
    if not os.path.isfile(file):
        raise FileNotFoundError(f"File '{file}' was not found.")
    fileType = file[-3:len(file)]
    print(fileType)
    if fileType in ["csv"]:
        graph = pd.read_csv(file)
    elif fileType in ["dat"]:
        if delim in [" ", "space", " "]:
            graph = pd.read_csv(file, delim_whitespace = True)
        elif delim in ["comma", ","]:
            graph = pd.read_csv(file)
    elif fileType in ["txt"]:
        if delim in [" ", "space"]:
            graph = pd.read_csv(file, delim_whitespace = True)
        elif delim in ["comma", ","]:
            graph = pd.read_csv(file)
    
    #graph = pd.read_csv("TimeSeriesData.csv")
    #graph = pd.read_csv("NarK_h2p_V.dat", delim_whitespace=True)
    #graph = pd.read_csv("NarK_h2p_TM4c_RMSD.dat", delim_whitespace=True)
    
    
    # ---- NaN handling ----
    
    if graph.isna().any().any():

        if warn_on_nan:
            warnings.warn("Missing values detected in input graph.")

        if nan_policy == "reject":
            raise ValueError("Input graph contains NaN or empty values.")

        elif nan_policy == "drop_rows":
            graph = graph.dropna(axis=0)

        elif nan_policy == "drop_cols":
            graph = graph.dropna(axis=1)

    # Convert after validation
    readGraph = graph.to_numpy()
    
    
        
    #titles
    try:
        readGraph = readGraph[0:].astype('float64')
        print("No title could be read. (Continuing with rest of program)")
        titles = []
        titles.append("Time") #Assume Time is the First Column
        for i in range(len(readGraph[0, :])-1):
            titles.append("Filler Title")
    except ValueError:
        titles = readGraph[0, :]
        readGraph = readGraph[1:].astype('float64')
    
    
    
    #Checking and converting user values
    try:
        ts = float(ts)
    except ValueError:
        print("The inputted start time (ts) of \'" + ts + "\' is not valid.")
        print("Exiting program")
        sys.exit()
    try:
        m = int(m)
    except ValueError:
        print("The inputted m-value of \'" + m + "\' is not valid.")
        print("Exiting program")
        sys.exit()
    try:
        colRead = int(colRead)
    except ValueError:
        print("The inputted column read value of \'" + colRead + "\' is not valid.")
        print("Exiting program")
        sys.exit()
    try:
        alphaValue = float(alphaValue)
    except ValueError:
        print("The inputted alpha value of \'" + alphaValue + "\' is not valid.")
        print("Exiting program")
        sys.exit()
    
    
    if not (n==None):
        try:
            n = int(n)
        except ValueError:
            print("The inputted n value of \'" + n + "\' is not valid.")
            deltaT = readGraph[1][0] - readGraph[0][0]
            npt = int(len(readGraph)-(ts/deltaT))
            n = npt//m
            print("Automatically using max n-value of " + str(n) + " based off the other parameters.\n")
            
    else:
        deltaT = readGraph[1][0] - readGraph[0][0]
        npt = int(len(readGraph)-(ts/deltaT))
        n = npt//m

    if n<24:
        print("NOTE THE INPUTTED n-value OF \'" + str(n) + "\' is LESS THAN 24. THE FOLLOWING STATISTICAL RESULTS ARE INVALID DUE TO n BEING LESS THAN 24.\n")

    cont = True
    while cont:
        outcome = runTest(file, readGraph, titles, colRead, ts, m, n, alphaValue)
        if outcome[0]:
            cont=False
            print("Found Equilibriation at: ")
            print("m = " + str(m))
            print("n = " + str(n))
            print("ts = " + str(ts))
        else:
            if not outcome[1][0]:
                ts+=(deltaT * len(readGraph)/300)
            elif not outcome[1][1]:
                m+=1
            npt = int(len(readGraph)-(ts/deltaT))
            n = npt//m
            
            if n<24:
                cont=False
                print("Could not find equilibriation parameters. N dropped below 24.")
    

                    
                    
def binaryFind(file, delim, colRead, ts, m, n, alphaValue):
    
    # ---- Guard: check if file exists ----
    if not os.path.isfile(file):
        raise FileNotFoundError(f"File '{file}' was not found.")
    fileType = file[-3:len(file)]
    if fileType in ["csv"]:
        graph = pd.read_csv(file)
    elif fileType in ["dat"]:
        if delim in [" ", "space"]:
            graph = pd.read_csv(file, delim_whitespace = True)
        elif delim in ["comma", ","]:
            graph = pd.read_csv(file)
    elif fileType in ["txt"]:
        if delim in [" ", "space"]:
            graph = pd.read_csv(file, delim_whitespace = True)
        elif delim in ["comma", ","]:
            graph = pd.read_csv(file)
    
    #graph = pd.read_csv("TimeSeriesData.csv")
    #graph = pd.read_csv("NarK_h2p_V.dat", delim_whitespace=True)
    #graph = pd.read_csv("NarK_h2p_TM4c_RMSD.dat", delim_whitespace=True)
    
    
    # ---- NaN handling ----
    
    if graph.isna().any().any():

        if warn_on_nan:
            warnings.warn("Missing values detected in input graph.")

        if nan_policy == "reject":
            raise ValueError("Input graph contains NaN or empty values.")

        elif nan_policy == "drop_rows":
            graph = graph.dropna(axis=0)

        elif nan_policy == "drop_cols":
            graph = graph.dropna(axis=1)

    # Convert after validation
    readGraph = graph.to_numpy()
    
    
        
    #titles
    try:
        readGraph = readGraph[0:].astype('float64')
        print("No title could be read. (Continuing with rest of program)")
        titles = []
        titles.append("Time") #Assume Time is the First Column
        for i in range(len(readGraph[0, :])-1):
            titles.append("Filler Title")
    except ValueError:
        titles = readGraph[0, :]
        readGraph = readGraph[1:].astype('float64')
    
    
    
    #Checking and converting user values
    try:
        ts = float(ts)
    except ValueError:
        print("The inputted start time (ts) of \'" + ts + "\' is not valid.")
        print("Exiting program")
        sys.exit()
    try:
        m = int(m)
    except ValueError:
        print("The inputted m-value of \'" + m + "\' is not valid.")
        print("Exiting program")
        sys.exit()
    try:
        colRead = int(colRead)
    except ValueError:
        print("The inputted column read value of \'" + colRead + "\' is not valid.")
        print("Exiting program")
        sys.exit()
    try:
        alphaValue = float(alphaValue)
    except ValueError:
        print("The inputted alpha value of \'" + alphaValue + "\' is not valid.")
        print("Exiting program")
        sys.exit()
    
    
    if not (n==None):
        try:
            n = int(n)
        except ValueError:
            print("The inputted n value of \'" + n + "\' is not valid.")
            deltaT = readGraph[1][0] - readGraph[0][0]
            npt = int(len(readGraph)-(ts/deltaT))
            n = npt//m
            print("Automatically using max n-value of " + str(n) + " based off the other parameters.\n")
            
    else:
        deltaT = readGraph[1][0] - readGraph[0][0]
        npt = int(len(readGraph)-(ts/deltaT))
        n = npt//m

    if n<24:
        print("NOTE THE INPUTTED n-value OF \'" + str(n) + "\' is LESS THAN 24. THE FOLLOWING STATISTICAL RESULTS ARE INVALID DUE TO n BEING LESS THAN 24.\n")


    
    
    allEqPoints = []
    while m<=512: 
        equilPoints = []
        hi = readGraph[(len(readGraph)-1)][0]
        lo = readGraph[0][0]
        #ts = readGraph[len(readGraph)//2][0]
        #ts = readGraph[0][0]

        npt = int(len(readGraph)-(ts/deltaT))
        n = npt//m
        cont = True
        while cont:
        
            if n<24:
                diff = 24-n
                if diff<12:
                    print("TS BEFORE THE SLIDING: " + str(ts))
                    ts -= (diff*m*deltaT)
                    print("TS AFTER THE SLIDING: " + str(ts))
                    npt = int(len(readGraph)-(ts/deltaT))
                    n = npt//m
                else:
                    print("Could not find equilibriation parameters. N dropped too much below 24.")
                    cont = False
                    if (len(equilPoints)>0):
                        allEqPoints.append(equilPoints[len(equilPoints)-1])
            
                        
            if cont:
                outcome = runTest(file, readGraph, titles, colRead, ts, m, n, alphaValue)
                print("TS BEFORE BINARY ALTERATION: " + str(ts))

                if not outcome[1][0]:
                    lo = ts
                    ts = (ts+hi)/2
                    print("TS AFTER INCREASING BY HALF: " + str(ts))
                else:
                    if outcome[0]:
                        equilPoints.append([ts, m, n])
                    hi = ts
                    ts = (ts+lo)/2
                    print("TS AFTER DECREASING BY HALF: " + str(ts))

                npt = int(len(readGraph)-(ts/deltaT))
                n = npt//m
                            
                
                if (hi-lo) < deltaT:
                    
                    cont = False
                    if (outcome[1][0]):
                        if (outcome[1][1]):
                            allEqPoints.append([ts, m, n])
                    else:
                        if (len(equilPoints)>0):
                            allEqPoints.append(equilPoints[len(equilPoints)-1])
                        else:
                            print("No Equilibriation could be found.")
        m=math.floor(m*1.5)
        print("M-" +str(m))
        print(allEqPoints)
    print("\nThe following combinatioins of parameters are equilibriated:")
    for values in allEqPoints:
        print("ts-" + str(values[0]) + ", m-" + str(values[1]) + ", n-" + str(values[2]) )

        
        










    
#programmaticForm("NarK_h2p_heavy_RMSD", "dat", " ", 1, 0, 30, 50) 

if len(sys.argv)==8:    
    programmaticForm(*sys.argv[1:])
elif len(sys.argv)==7:
    programmaticForm(*sys.argv[1:], 0.05)
elif len(sys.argv)==6:
    programmaticForm(*sys.argv[1:], None, 0.05)
elif len(sys.argv) == 2:  #this means an input file
    arguments = [None] * 8
    arguments[7] = 0.05
    arguments[3] = 1
    
    data = open(sys.argv[1], "r")
    firstLine = (data.readline())
    if firstLine.lower().strip() in ["md test format"]:
        secondLine = (data.readline())
        testType = secondLine.split("-")
        
        if testType[0].lower() in ["run type", "run", "type", "runtype"]:
            if testType[1].lower().strip() in ["auto"]:
                print("Running repeating auto test:")
                for lines in data:
                    inputs = lines.split("-")
                    if inputs[0].lower() in ["file", "file name", "file path"]:
                        arguments[1] = inputs[1].strip()
                    elif inputs[0].lower() in ["delimitation", "delim", "separation", "sep"]:
                        arguments[2] = inputs[1].strip()
                    elif inputs[0].lower() in ["col", "colread", "column read", "col read"]:
                        arguments[3] = inputs[1].strip()
                    elif inputs[0].lower() in ["ts", "start time", "starting time", "starting data point"]:
                        arguments[4] = inputs[1].strip()
                    elif inputs[0].lower() in ["m", "mvalue", "m value"]:
                        arguments[5] = inputs[1].strip()

                    elif inputs[0].lower() in ["alpha", "alphavalue", "alpha value"]:
                        arguments[7] = inputs[1].strip()
                
                print(testType[2])
                if testType[2].lower().strip() in ["binary", "bin"]:
                    data.close()
                    print("Running Binary Search Test")
                    binaryFind(*arguments[1:])
                else:
                    data.close()
                    print("Running Sequential Test")
                    autoFind(*arguments[1:])
            else:
                for lines in data:
                    inputs = lines.split("-")
                    if inputs[0].lower() in ["file", "file name", "file path"]:
                        arguments[1] = inputs[1].strip()
                    elif inputs[0].lower() in ["delimination", "delim", "separation", "sep"]:
                        arguments[2] = inputs[1].strip()
                    elif inputs[0].lower() in ["col", "colread", "column read", "col read"]:
                        arguments[3] = inputs[1].strip()
                    elif inputs[0].lower() in ["ts", "start time", "starting time", "starting data point"]:
                        arguments[4] = inputs[1].strip()
                    elif inputs[0].lower() in ["m", "mvalue", "m value", "m-value"]:
                        arguments[5] = inputs[1].strip()
                    elif inputs[0].lower() in ["n", "nvalue", "n value", "n-value"]:
                        try:
                            inputs[1] = int(inputs[1].strip())
                            arguments[6] = inputs[1]
                        except ValueError:
                            print("USING MAX N!")
                    elif inputs[0].lower() in ["alpha", "alphavalue", "alpha value"]:
                        arguments[7] = inputs[1].strip()
                data.close()
                programmaticForm(*arguments[1:])
        else:
            print("Format invalid. Second line needs to include the header \"run type\"")
            data.close()
            sys.exit()
    else:
        print("Unrecognized format")
        data.close()
        sys.exit()

    
    
    
    #Input file

else:
 
    file = input("Enter the file: ")
    # ---- Guard: check if file exists ----
    if not os.path.isfile(file):
        raise FileNotFoundError(f"File '{file}' was not found.")

    typeOfFile = file[-3:len(file)]
    
    if typeOfFile in ["csv"]:
        graph = pd.read_csv(file)
    elif typeOfFile in ["dat"]:
        delimiter = input("enter delimination (space or comma): ")
        if delimiter in ["space"]:
            graph = pd.read_csv(file, delim_whitespace=True)
        elif delimiter in ["comma"]:
            graph = pd.read_csv(file)
    elif typeOfFile in ["txt"]:
        if delimiter in [" ", "space"]:
            graph = pd.read_csv(file, delim_whitespace = True)
        elif delimiter in ["comma", ","]:
            graph = pd.read_csv(file)
    else:
        print("Type of file not recognize (only support .csv and .dat files)")
        sys.exit()

    #graph = pd.read_csv("TimeSeriesData.csv")
    #graph = pd.read_csv("NarK_h2p_V.dat", delim_whitespace=True)
    #graph = pd.read_csv("NarK_h2p_TM4c_RMSD.dat", delim_whitespace=True)






    # ---- NaN handling ----
    
    if graph.isna().any().any():

        if warn_on_nan:
            warnings.warn("Missing values detected in input graph.")

        if nan_policy == "reject":
            raise ValueError("Input graph contains NaN or empty values.")

        elif nan_policy == "drop_rows":
            graph = graph.dropna(axis=0)

        elif nan_policy == "drop_cols":
            graph = graph.dropna(axis=1)

    # Convert after validation
    readGraph = graph.to_numpy()

    
    
    
    titled = True
    try:
        readGraph = readGraph[0:].astype('float64')
        print("No titles could be read.")
        titles = []
        titles.append("Time") #Assume Time is the First Column
        for i in range(len(readGraph[0, :])-1):
            titles.append("Filler Title")
        titled = False
    except ValueError:
        titles = readGraph[0, :]
        readGraph = readGraph[1:].astype('float64')

    dataReadIndex = 1
    if len(readGraph[0,:])>2:
        cont = True
        while cont:
            temp = (input("Which column (by index) is read in addition to time (index = 0): "))
            if temp.isnumeric():
                if (int(temp) < len(readGraph[0,:])) and (int(temp)>0):
                    dataReadIndex = int(temp)
                    cont = False
                else:
                    print("The index entered is not within the data provided (either too small or too large)")
            else:
                print("The value entered is not a valid index number.")
                
    if not titled:
        titles[dataReadIndex] = input("Enter Title for the selected Column: ")
        
    
        
        
    #testing purposes
    #readGraph = np.transpose(readGraph)
    #readGraph[1] = 0.00025*readGraph[0]+readGraph[1]
    #readGraph = np.transpose(readGraph)
    ###




    initialGraph = np.transpose(readGraph)
    #plt.title("Initial Graph: Time vs " + titles[dataReadIndex]) 
    plt.title("Initial Graph: Time vs Observable") 
    plt.xlabel(titles[0]) #Should be time
    plt.ylabel(titles[dataReadIndex]) 
    plt.plot(initialGraph[0],initialGraph[dataReadIndex])
    plt.show()
    
    cont = True
    while cont:
        alphaValue = (input("Input an alpha value to be used (decimal form): "))
        if isValidNumber(alphaValue):
            cont = False
            alphaValue = float(alphaValue)
        else:
            print("Not a valid number, try again.")


    overallTestCont = True
    while(overallTestCont):
        ts = 0
        cont = True
        while cont:
            ts = (input("Input start time: "))
            if isValidNumber(ts):
                cont = False
                ts = float(ts)
            else:
                print("Not a valid number, try again.")
        deltaT = readGraph[1][0] - readGraph[0][0]
        
        
        
        
        #minimum m should be 25
        #medium should be 100
        #400 should be most powerful
        
        m=1
        cont = True
        while cont:
            
            cont1 = True
            while cont1:    
                m=(input("Enter m value (how many points in each segment): "))
                if(m.isnumeric()):
                    m = int(m)
                    cont1 = False
                else:
                    print("Not a valid number, please try again.")
        
        
            npt = int(len(readGraph)-(ts/deltaT))
            maxN = npt//m
            if(maxN>=24):
                cont=False
            else:
                print("The max n of " + str(maxN) + " is less than 24, please pick a smaller m that allows n to be greater than 24 for reliable power")
        print("max n=" + str(maxN))
        
        cont = True
        while cont:    
            n = (input("Enter n value (at least 24 for reasonable power): "))
            if(n.isnumeric()):
                n = int(n)
                cont = False
            else:
                print("Not a valid number, please try again.")
            
        runTest(file, readGraph, titles, dataReadIndex, ts, m, n, alphaValue)        
        
        
        continueTests = input("\n\nContinue testing on same data? (Y/N): ")
        if continueTests.lower() in ["n", "no", "stop", "end"]:
            overallTestCont = False





