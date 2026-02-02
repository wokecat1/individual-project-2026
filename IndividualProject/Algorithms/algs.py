# ticker = string
# price = number
# multiplier = number
# name = string
# stock_ticker = string
# stock_price = number

import backtrader as bt
import argparse
import pandas as pd
from Database import db

class SmaCross(bt.SignalStrategy):
    def __init__(self):
        sma1, sma2 = bt.ind.SMA(period=10), bt.ind.SMA(period=30)
        crossover = bt.ind.CrossOver(sma1, sma2)
        self.signal_add(bt.SIGNAL_LONG, crossover)

def run(frames):
    cerebro = bt.Cerebro()
    cerebro.addstrategy(SmaCross)
    for i in range(db.frames.__len__()):
        data = frames[i]
        data_feed = bt.feeds.PandasData(dataname=data)
        cerebro.adddata(data_feed)

    cerebro.run()
    cerebro.plot(style='bar')
