from os.path import exists
import matplotlib.pyplot as plt
import pandas as pd

from Graphing.colors import colors

def graph(file_name):
    if exists ('Data/' + file_name):
        # Create data frame for CSV file
        df = pd.read_csv('Data/' + file_name)
        headers = df.columns.values.tolist()
        stdev = []

        # Iterate through columns and plot each onto graph
        for i in range(headers.__len__() - 1):
            # Exclude 'Day' column of CSV file
            column_name = str(headers[i + 1])
            std = float(df[headers[i + 1]].std())
            plt.plot(df['Day'], df[column_name], color=colors[i], label=column_name)
            stdev += (column_name, round(std, 6))
        plt.xlabel('Day')
        plt.ylabel('Stock Price ($)')
        plt.title('Stock Price During Simulation Scenario')
        plt.grid(True)
        plt.show()
        print (stdev)
    else:
        print('File not found, please check your spelling and capitalisation')