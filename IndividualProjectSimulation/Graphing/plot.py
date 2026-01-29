import mysql.connector
import matplotlib.pyplot as plt
import pandas as pd

from sqlalchemy import create_engine
from Environment import dataExport, db
from Graphing.colors import colors

def graph(ticker):
    if ticker in dataExport.tickers:
        # Create data frame for CSV file
        try:
            # Read data for stock from database
            conn = create_engine(db.conn_str)
            df = pd.read_sql('SELECT * FROM ' + ticker, con=conn, index_col='Day')
            conn.close()

            # Plot closing price of stock
            headers = df.columns.values.tolist()
            column_name = str(headers[4]) # Closing price column
            plt.plot(df['Date'], df[column_name], color=darkturquoise, label=column_name)
            plt.xlabel('Date')
            plt.ylabel('Stock Closing Price ($)')
            plt.title('Stock Price During Simulation Scenario')
            plt.grid(True)
            plt.show()
        except Exception as e:
            print('Error importing data: ' + e)
    else:
        print('Invalid ticker entered')
        print('List of valid tickers: ' + dataExport.tickers)