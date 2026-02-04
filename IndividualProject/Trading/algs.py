# ticker = string
# price = number
# multiplier = number
# name = string
# stock_ticker = string
# stock_price = number
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import itertools
import backtrader as bt

from Database import db


class SimpleSMA(bt.SignalStrategy):
    def __init__(self):
        self.inds = {}
        for i, d in enumerate(self.datas):
            sma = bt.ind.MovingAverageSimple(d.close, period=15)
            self.inds[d] = bt.ind.CrossOver(d.close, sma)

    def next(self):
        for i, d in enumerate(self.datas):
            if self.inds[d] > 0.0:  # cross upwards
                self.buy(data=d)

            elif self.inds[d] < 0.0:
                self.close(data=d)

class SimpleMACD(bt.SignalStrategy):
    def __init__(self):
        self.inds = {}
        for i, d in enumerate(self.datas):
            macd = bt.ind.MACD(d.close)
            sig = bt.ind.MACD(macd)
            self.inds[d] = (macd, sig)

    def next(self):
        for i, d in enumerate(self.datas):
            if self.inds[d][0] < self.inds[d][1]:
                self.buy(data=d)
            elif self.inds[d][0] > self.inds[d][1]:
                self.close(data=d)

class SMACrossover(bt.SignalStrategy):
    # list of parameters which are configurable for the strategy
    params = dict(
        pfast=10,  # period for the fast moving average
        pslow=30  # period for the slow moving average
    )

    def __init__(self):
        self.inds = {}
        for i, d in enumerate(self.datas):
            sma1 = bt.ind.SMA(period=self.p.pfast)  # fast moving average
            sma2 = bt.ind.SMA(period=self.p.pslow)  # slow moving average
            self.inds[d] = bt.ind.CrossOver(sma1, sma2)  # crossover signal

    def next(self):
        for i, d in enumerate(self.datas):
            if not self.position:  # not in the market
                if self.inds[d] > 0:  # if fast crosses slow to the upside
                    self.buy(data=d)  # enter long

            elif self.inds[d] < 0:  # in the market & cross to the downside
                self.close(data=d)  # close long position

def runall(frames):

    # Create the 1st data
    for i, frame in enumerate(frames):
        # Create a cerebro
        cerebro = bt.Cerebro()

        # Add data frames to cerebro as data feeds
        ticker_name = str(db.tickers[i]) if i < len(db.tickers) else f"Ticker_{i}"
        data_feed = bt.feeds.PandasData(dataname=frame)
        cerebro.adddata(data_feed, name=ticker_name)

        # Add the strategy
        cerebro.addstrategy(SimpleSMA)

        # Add cash
        cerebro.broker.setcash(10000)

        # And run it
        print('Starting Portfolio Value: %.2f' % cerebro.broker.getvalue())
        cerebro.run()
        print('Final Portfolio Value: %.2f' % cerebro.broker.getvalue())

        # Plot if requested
        cerebro.plot(style='candlestick', numfigs=1)

def runone(ticker):

    # Create a cerebro
    cerebro = bt.Cerebro()

    # Add data frames to cerebro as data feeds
    frame = db.frames[db.tickers.index(ticker)]
    data_feed = bt.feeds.PandasData(dataname=frame)
    cerebro.adddata(data_feed, name=ticker)

    # Add the strategy
    cerebro.addstrategy(SMACrossover)

    # Add cash
    cerebro.broker.setcash(10000)

    # And run it
    print('Starting Portfolio Value: %.2f' % cerebro.broker.getvalue())
    cerebro.run()
    print('Final Portfolio Value: %.2f' % cerebro.broker.getvalue())

    # Plot if requested
    cerebro.plot(style='candlestick', numfigs=1)