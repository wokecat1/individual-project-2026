import mysql.connector
import MySQLdb
import pandas as pd
# import pandas_datareader.data as web

from sqlalchemy import create_engine
from Database import db

tickers = ['AAOI', 'BTDR', 'ENR', 'IMAX', 'JACK',
            'MAPS', 'NTGR', 'PLSE', 'SAFX', 'SCHL',
            'STRL', 'SWX', 'TSE', 'TVGN', 'USAU', 'WDFC']

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



"""def export_data(ticker):
    data = web.DataReader(ticker, 'stooq')
    df = pd.DataFrame(data)
    try:
        engine = create_engine(db.conn_str)
        df.to_sql(ticker, con=engine, if_exists='replace')
    except MySQLdb.Error:
        print("Can't connect to database")
        return None
    except Exception as e:
        print(e)"""

def import_data(v):
    try:
        engine = create_engine(db.conn_str)
        conn = engine.connect()
        frames = []
        for i in range(tickers.__len__()):
            ticker_data = conn.execute(
                "SELECT * FROM " + tickers[i] + " WHERE Date BETWEEN " + scenarios[v - 1][0] + " AND " + scenarios[v - 1][1] + " ORDER BY Date"
            )
            df = pd.DataFrame(ticker_data)
            df.columns = ticker_data.keys()
            frames.append(df)

    except MySQLdb.Error:
        print("Can't connect to database")
        return None
    except Exception as e:
        print(e)

import_data(2)