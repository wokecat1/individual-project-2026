import mysql.connector
import MySQLdb
import pandas as pd

from sqlalchemy import create_engine, text
from Application import SUCCESS, DB_READ_ERROR, DB_WRITE_ERROR, INPUT_ERROR

# Database connection info
hostname = 'krier.uscs.susx.ac.uk'
username = 'kg412'
password = 'Mysql_627075'
database = 'kg412'
conn_str = 'mysql+mysqlconnector://' + username + ':' + password + '@' + hostname + '/' + database

# List of tickers which have data stored in database
tickers = ['AAOI', 'BTDR', 'ENR', 'IMAX', 'JACK',
            'MAPS', 'NTGR', 'PLSE', 'SAFX', 'SCHL',
            'STRL', 'SWX']

pennytickers = ['TSE', 'TVGN', 'USAU', 'WDFC']

# List of historical scenario start and end dates
scenarios = [("2025-07-29", "2026-01-28"),
             ("2025-01-29", "2025-07-28"),
             ("2024-07-29", "2025-01-28"),
             ("2024-01-29", "2024-07-28"),
             ("2023-07-29", "2024-01-28"),
             ("2023-01-29", "2023-07-28"),
             ("2022-07-29", "2023-01-28"),
             ("2022-01-29", "2022-07-28"),
             ("2021-07-29", "2022-01-28"),
             ("2021-01-29", "2021-07-28"),
             ]

# Array of ticker data frames for exporting
frames = []

'''def export_data(ticker):
    """Internal function: export ticker data to database for storage."""
    data = web.DataReader(ticker, 'stooq')
    df = pd.DataFrame(data)
    try:
        engine = create_engine(db.conn_str)
        df.to_sql(ticker, con=engine, if_exists='replace')
    except MySQLdb.Error:
        print("Can't connect to database")
        return None
    except Exception as e:
        print(e)'''

def import_data(v):
    """Import stock data for a specific scenario from the database. Takes a value from 1-16 as input."""
    if v in range(1, 16):
        try:
            engine = create_engine(conn_str)
            start_date, end_date = scenarios[v - 1]
            with engine.connect() as conn:
                for ticker in tickers:
                    # Query ticker data between start and end dates
                    query = text(f"SELECT * FROM {ticker} WHERE Date BETWEEN :start AND :end ORDER BY Date")

                    # Read SQL into DataFrame using start and end dates as parameters, then add to frames array
                    df = pd.read_sql(query, conn, params={"start": start_date, "end": end_date})
                    df['Date'] = pd.to_datetime(df['Date'])
                    df = df.set_index('Date')
                    frames.append(df)
                    if len(frames) == len(tickers):
                        return SUCCESS

        except MySQLdb.Error:
            print("Can't connect to database")
            return DB_READ_ERROR
    else:
        print("Error: invalid input")
        return INPUT_ERROR