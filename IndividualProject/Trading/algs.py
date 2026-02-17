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
import numpy as np
from math import floor

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

class MACD(bt.SignalStrategy):
    params = (
        ('fast_period', 12),
        ('slow_period', 26),
        ('sig_period', 9),
    )

    def __init__(self):
        self.inds = {}
        for i, d in enumerate(self.datas):
            macd_obj = bt.ind.MACD(d.close,                                     # MACD line
                                       period_me1=d.params.fast_period,
                                       period_me2 = d.params.slow_period,
                                       period_signal = d.params.sig_period)
            macd_crossover = bt.ind.CrossOver(macd_obj.macd, macd_obj.signal)   # crossover between MACD and EMA of MACD
            self.inds[d] = (macd_crossover)

    def next(self):
        for i, d in enumerate(self.datas):
            if not self.position:
                if self.inds[d] > 0:     # upward crossover
                    self.buy(data=d)
                elif self.inds[d] < 0:   # downward crossover
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

# relative strength index
class RSI(bt.SignalStrategy):
    params = (
        ('period', 14),     # window length
        ('overbought', 70), # overbought indicator
        ('oversold', 30)    # oversold indicator
    )

    def __init__(self):
        self.inds = {}
        for i, d in enumerate(self.datas):
            self.inds[d] = bt.ind.RSI(d.close, period=d.params.period)

    def next(self):
        for i, d in enumerate(self.datas):
            if not d.position and self.inds[d] < d.params.oversold:
                self.buy(data=d)
            elif d.position and self.inds[d] > d.params.overbought:
                self.close(data=d)

class BollingerBands(bt.SignalStrategy):
    params = (
        ('period', 20),
        ('devfactor', 2),
    )

    def __init__ (self):
        self.inds = {}
        for i, d in enumerate(self.datas):
            self.inds[d] = bt.ind.BollingerBands(d.close, period=self.params.period, devfactor = self.params.devfactor)

    def next(self):
        for i, d in enumerate(self.datas):
            if not d.position and d.close[0] < self.inds[d][3].lines.bot[0]: # price closes below lower bollinger band
                d.buy()
            elif d.position:
                if d.close[0] > self.inds[d].lines.top[0]:      # price closes above upper band
                    self.close(data=d)
                elif d.close[0] < self.inds[d].lines.mid[0]:    #price closes below middle band (alternate exit)
                    self.close(data=d)

# Vol osc divergence index
class VolOscDivergence(bt.SignalStrategy):
    params = (
        ('vol_window', 30),             # volatility calc period
        ('vol_roc_period', 7),          # ROC period for volatility oscillator
        ('price_lookback', 7),          # price change lookback period
        ('sma_window', 30),             # SMA window
        ('atr_window', 14),             # ATR window for stops
        ('atr_multiplier', 2),          # ATR multiplier
        ('rsi_window', 14),             # RSI window
        ('max_hold_bars', 30),          # Max position hold time
        ('min_gap_bars', 1),            # Minimum gap between trades
    )

    def __init__(self):
        self.inds = {}
        for i, d in enumerate(self.datas):
            # volatility oscillator
            returns = bt.ind.PctChange(d.close, period=1)               # 1-day % returns of closing price
            vol = bt.ind.StdDev(returns, period=self.params.vol_window)    # 20-day std dev of returns (volatility)
            vol_osc = bt.ind.ROC(vol, period=self.params.vol_roc_period)   # 5-day rate of change of volatility (shifts in market activity)

            sma = bt.ind.SMA(d.close, period=self.params.sma_window)       # 30-day simple moving average (confirming market trend)
            atr = bt.ind.ATR(d, period=self.params.atr_window)             # 14-day average true range (trailing stops, position sizing)
            rsi = bt.ind.RSI(period=self.params.rsi_window)                # 14-day relative strength index (filter overbought or oversold conditions)

            self.inds[d] = (returns, vol, vol_osc, sma, atr, rsi, None, None, None)

    def next(self):
        for i, d in enumerate(self.datas):
            if len(d) < 50: # need enough data for all indicators to be stable
                return

            current_price = d.close[0]

            # Closes positions on hold limit (30 days) to limit exposure
            if self.position and self.inds[d][6]: # entry bar
                if (len(d) - self.inds[d][6]) >= self.params.max_hold_bars:
                    self.close(data=d)
                    self.inds[d] = self.inds[d][:5] + (
                        None,  # reset entry bar
                        len(d),  # set last trade bar
                    ) + (self.inds[d][8],)
                    return

            # Trailing stops
            if self.position and self.inds[d][8]:
                # Long positions: exit if price falls below stop (current_price - (3 * ATR))
                if self.position.size > 0 and current_price <= self.inds[d][8]:
                    self.close(data=d)
                    self.inds[d] = self.inds[d][:5] + (
                        None,  # reset entry bar
                        len(d),  # set last trade bar
                    ) + (self.inds[d][8],)
                    return

                # Short positions: exit if price rises above stop (current_price + (3 * ATR))
                elif self.position.size < 0 and current_price >= self.inds[d][8]:
                    self.close(data=d)
                    self.inds[d] = self.inds[d][:5] + (
                        None,  # reset entry bar
                        len(d),  # set last trade bar
                    ) + (self.inds[d][8],)
                    return

            # Update trailing stop to save profits after a trade
            if self.position:
                if self.position.size > 0:
                    new_stop_price = current_price - self.params.atr_multiplier * self.inds[d][4][0]
                    if self.inds[d][8] is None or new_stop_price > self.inds[d][8]:
                        self.inds[d] = self.inds[d][:7] + (new_stop_price, )

            # Leave 1 bar between trades to avoid too rapid of a re-entry
            if self.inds[d][7] and (len(d) - self.inds[d][7]) < self.params.min_bars:
                return

            # Entry signals
            if not self.position:
                price_change = d.close[0] - d.close[-self.params.price_lookback]
                vol_osc_change = self.inds[d][2][0] - self.inds[d][2][-self.params.price_lookback]

                # Position size adjusted for volatility
                pct_atr = self.inds[d][4][0] / current_price
                size_factor = min(0.8, max(0.2, 0.1 / pct_atr)) if pct_atr > 0 else 0.5
                cash = self.broker.getcash()
                size = int(cash * size_factor / current_price)

                # Bullish divergence (price up, vol osc down, uptrend, RSI not overbought)
                # Enter long position with ATR stop
                if price_change < 0 < vol_osc_change and current_price > self.inds[d][3][0] and self.inds[d][5] < 70 and size > 0:
                    self.buy(data=d, size=size)
                    self.inds[d] = self.inds[d][:5] + (
                        len(d),  # set entry bar
                        len(d),  # set last trade bar
                        (current_price + self.params.atr_multiplier * self.inds[d][4][0]),  # set stop price
                    )

                # Bearish divergence (price down, vol osc up, downtrend, RSI not oversold)
                # Enter short position with ATR stop
                elif price_change < 0 < vol_osc_change and current_price < self.inds[d][3][0] and self.inds[d][5] > 30 and size > 0:
                    self.sell(data=d, size=size)
                    self.inds[d] = self.inds[d][:5] + (
                        len(d),                                                                 # set entry bar
                        len(d),                                                                 # set last trade bar
                        (current_price + self.params.atr_multiplier * self.inds[d][4][0]),     # set stop price
                    )


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
    cerebro.addstrategy(VolOscDivergence)

    # Add cash
    cerebro.broker.setcash(10000)

    # And run it
    print('Starting Portfolio Value: %.2f' % cerebro.broker.getvalue())
    cerebro.run()
    print('Final Portfolio Value: %.2f' % cerebro.broker.getvalue())

    # Plot if requested
    cerebro.plot(style='candlestick', numfigs=1)