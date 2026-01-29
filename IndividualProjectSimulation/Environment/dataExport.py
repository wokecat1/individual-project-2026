import mysql.connector
import MySQLdb
import pandas as pd
import pandas_datareader.data as web

from sqlalchemy import create_engine
from Environment import db

tickers = ['AAOI', 'BTDR', 'ENR', 'IMAX', 'JACK',
            'MAPS', 'NTGR', 'PLSE', 'SAFX', 'SCHL',
            'STRL', 'SWX', 'TSE', 'TVGN', 'USAU', 'WDFC']

def export(ticker):
    data = web.DataReader(ticker, 'stooq')
    df = pd.DataFrame(data)
    try:
        conn = create_engine(db.conn_str)
        df.to_sql(ticker, con=conn, if_exists='replace')
    except MySQLdb.Error:
        print("Can't connect to database")
        return None
    except Exception as e:
        print(e)

for i in range(len(tickers)):
    export(tickers[i])


