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

start_cash = 10000
max_hold_bars = 30
min_gap_bars = 1

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
        ('period', 14),         # window length
        ('overbought', 70),     # overbought indicator
        ('oversold', 35),       # oversold indicator
        ('max_hold_bars', max_hold_bars),
        ('min_gap_bars', min_gap_bars),
    )

    def __init__(self):
        self.inds = {}
        for i, d in enumerate(self.datas):
            rsi = bt.ind.RSI(d.close, period=self.params.period)
            rsi_ma = bt.ind.SMA(rsi, period=5)  # short-term moving average of RSI

            self.inds[d] = {
                'rsi': rsi,
                'rsi_peak': None,
                'entry_bar': None,
                'last_trade_bar': None,
                'stop_rsi': None
            }

    def next(self):
        for i, d in enumerate(self.datas):
            if len(d) < 30:
                continue

            current_price = d.close[0]
            current_rsi = self.inds[d]['rsi'][0]
            pos = self.getposition(d)

            # Closes positions on hold limit (30 days) to limit exposure
            if pos and self.inds[d]['entry_bar']:  # entry bar
                if (len(d) - self.inds[d]['entry_bar']) >= self.params.max_hold_bars:
                    self.close(data=d)
                    self.inds[d]['entry_bar'] = None
                    self.inds[d]['last_trade_bar'] = len(d)
                    continue

            # Trailing stops
            if pos:
                # Initialize peak if missing
                if self.inds[d]['rsi_peak'] is None:
                    self.inds[d]['rsi_peak'] = current_rsi

                # Long position
                if pos.size > 0:
                    self.inds[d]['rsi_peak'] = max(self.inds[d]['rsi_peak'], current_rsi)
                    if current_rsi < self.inds[d]['rsi_peak'] - 5:
                        self.close(data=d)
                        self.inds[d]['rsi_peak'] = None
                        continue

                # Short position
                elif pos.size < 0:
                    self.inds[d]['rsi_peak'] = min(self.inds[d]['rsi_peak'], current_rsi)
                    if current_rsi > self.inds[d]['rsi_peak'] + 5:
                        self.close(data=d)
                        self.inds[d]['rsi_peak'] = None
                        continue

            # Update trailing stop to save profits after a trade
            if pos:
                if pos.size > 0:
                    new_peak_rsi = max(self.inds[d]['rsi_peak'], current_rsi)
                    if self.inds[d]['rsi_peak'] is None or new_peak_rsi > self.inds[d]['rsi_peak']:
                        self.inds[d]['rsi_peak'] = new_peak_rsi
                else:
                    new_peak_rsi = min(self.inds[d]['rsi_peak'], current_rsi)
                    if self.inds[d]['rsi_peak'] is None or new_peak_rsi < self.inds[d]['rsi_peak']:
                        self.inds[d]['rsi_peak'] = new_peak_rsi

            rsi_slope = self.inds[d]['rsi'][0] - self.inds[d]['rsi'][-3]
            trend_strength = abs(rsi_slope)
            size_factor = min(1.0, max(0.2, trend_strength / 10))
            cash = self.broker.getcash()
            size = int(cash * size_factor / current_price)
            if size <= 0:
                continue

            # Entry conditions
            if not pos and current_rsi < self.p.oversold and rsi_slope > 0:
                self.buy(data=d, size=size)
                self.inds[d]['rsi_peak'] = current_rsi

            elif pos and current_rsi > self.p.overbought and rsi_slope < 0:
                self.sell(data=d, size=size)
                self.inds[d]['rsi_peak'] = current_rsi

class BollingerBands(bt.SignalStrategy):
    params = (
        ('period', 20),                     # period for SMA middle band
        ('devfactor', 2),                   # std dev for upper/lower bands
        ('warning_multiplier', 0.04),       # Grace period multiplier around bands
        ('max_hold_bars', max_hold_bars),
        ('min_gap_bars', min_gap_bars),
    )

    def __init__ (self):
        self.inds = {}
        for i, d in enumerate(self.datas):
            bbands = bt.ind.BollingerBands(d.close, period=self.params.period, devfactor = self.params.devfactor)
            self.inds[d] = {
                'bbands': bbands,                   # full bollinger band data
                'upper': bbands.top,     # upper band
                'middle': bbands.mid,   # middle band
                'lower': bbands.bot,     # lower band
                'entry_bar': None,
                'last_trade_bar': None,
                'stop_price': None
            }

    def next(self):
        for i, d in enumerate(self.datas):
            if len(d) < 30:
                continue

            current_price = d.close[0]
            pos = self.getposition(d)

            # Closes positions on hold limit (30 days) to limit exposure
            if pos and self.inds[d]['entry_bar'] is not None:  # entry bar
                if (len(d) - self.inds[d]['entry_bar']) >= self.params.max_hold_bars:
                    self.close(data=d)
                    self.inds[d]['entry_bar'] = None
                    self.inds[d]['last_trade_bar'] = len(d)
                    self.inds[d]['stop_price'] = None
                    continue

            # Trailing stops
            if pos and self.inds[d]['stop_price']:
                # Long positions: exit if price closes 4% below lower band
                if pos.size > 0 and current_price < self.inds[d]['stop_price']:
                    self.close(data=d)
                    self.inds[d]['entry_bar'] = None
                    self.inds[d]['last_trade_bar'] = len(d)
                    self.inds[d]['stop_price'] = None
                    continue

                # Short positions: exit if price closes 4% above upper band
                elif pos.size < 0 and current_price > self.inds[d]['stop_price']:
                    self.close(data=d)
                    self.inds[d]['entry_bar'] = None
                    self.inds[d]['last_trade_bar'] = len(d)
                    self.inds[d]['stop_price'] = None
                    continue

            # Update trailing stop to save profits after a trade
            if pos:
                if pos.size > 0:
                    new_stop_price = (1 - self.params.warning_multiplier) * self.inds[d]['lower'][0]
                    if self.inds[d]['stop_price'] is None or new_stop_price > self.inds[d]['stop_price']:
                        self.inds[d]['stop_price'] = new_stop_price
                else:
                    new_stop_price = (1 + self.params.warning_multiplier) * self.inds[d]['upper'][0]
                    if self.inds[d]['stop_price'] is None or new_stop_price < self.inds[d]['stop_price']:
                        self.inds[d]['stop_price'] = new_stop_price

            # Leave 1 bar between trades to avoid too rapid of a re-entry
            if self.inds[d]['last_trade_bar'] and (len(d) - self.inds[d]['last_trade_bar']) < self.params.min_gap_bars:
                continue

            # Trading size adjusted for width of bands
            pct_width = (self.inds[d]['upper'][0] - self.inds[d]['lower'][0]) / current_price
            size_factor = min(0.8, max(0.2, 0.1 / pct_width)) if pct_width > 0 else 0.5
            cash = self.broker.getcash()
            size = int(cash * size_factor / current_price)
            if size <= 0:
                continue

            # Entry conditions
            if not pos:
                # Enter long position if price closes above upper band
                if current_price > self.inds[d]['upper'][0]:
                    self.buy(data=d, size=size)
                    self.inds[d]['entry_bar'] = len(d)
                    self.inds[d]['last_trade_bar'] = len(d)
                    self.inds[d]['stop_price'] = (1 - self.params.warning_multiplier) * self.inds[d]['lower'][0]    # Stop price 2% lower than lower band

                # Enter short position if price closes below lower band
                elif current_price < self.inds[d]['lower'][0]:
                    self.sell(data=d, size=size)
                    self.inds[d]['entry_bar'] = len(d)
                    self.inds[d]['last_trade_bar'] = len(d)
                    self.inds[d]['stop_price'] = (1 + self.params.warning_multiplier) * self.inds[d]['upper'][0]   # Stop price 2% higher than upper band

# Vol osc divergence index
class VolOscDivergence(bt.SignalStrategy):
    params = (
        ('vol_window', 30),                 # volatility calc period
        ('vol_roc_period', 7),              # ROC period for volatility oscillator
        ('price_lookback', 7),              # price change lookback period
        ('sma_window', 30),                 # SMA window
        ('atr_window', 14),                 # ATR window for stops
        ('atr_multiplier', 2),              # ATR multiplier
        ('rsi_window', 14),                 # RSI window
        ('max_hold_bars', max_hold_bars),   # Max position hold time
        ('min_gap_bars', min_gap_bars),     # Minimum gap between trades
    )

    def __init__(self):
        self.inds = {}
        for i, d in enumerate(self.datas):
            # volatility oscillator
            returns = bt.ind.PctChange(d.close, period=1)                   # 1-day % returns of closing price
            vol = bt.ind.StdDev(returns, period=self.params.vol_window)     # 20-day std dev of returns (volatility)
            vol_osc = bt.ind.ROC(vol, period=self.params.vol_roc_period)    # 5-day rate of change of volatility (shifts in market activity)

            sma = bt.ind.SMA(d.close, period=self.params.sma_window)        # 30-day simple moving average (confirming market trend)
            atr = bt.ind.ATR(d, period=self.params.atr_window)              # 14-day average true range (trailing stops, position sizing)
            rsi = bt.ind.RSI(d.close, period=self.params.rsi_window)        # 14-day relative strength index (filter overbought or oversold conditions)

            self.inds[d] = {
                'returns': returns,
                'vol': vol,
                'vol_osc': vol_osc,
                'sma': sma,
                'atr': atr,
                'rsi': rsi,
                'entry_bar': None,
                'last_trade_bar': None,
                'stop_price': None
            }

    def next(self):
        for i, d in enumerate(self.datas):
            if len(d) < 30: # need enough data for all indicators to be stable
                continue

            current_price = d.close[0]
            pos = self.getposition(d)

            # Closes positions on hold limit (30 days) to limit exposure
            if pos and self.inds[d]['entry_bar']: # entry bar
                if (len(d) - self.inds[d]['entry_bar']) >= self.params.max_hold_bars:
                    self.close(data=d)
                    self.inds[d]['entry_bar'] = None
                    self.inds[d]['last_trade_bar'] = len(d)
                    continue

            # Trailing stops
            if pos and self.inds[d]['stop_price']:
                # Long positions: exit if price falls below stop (current_price - (3 * ATR))
                if pos.size > 0 and current_price <= self.inds[d]['stop_price']:
                    self.close(data=d)
                    self.inds[d]['entry_bar'] = None
                    self.inds[d]['last_trade_bar'] = len(d)
                    continue

                # Short positions: exit if price rises above stop (current_price + (3 * ATR))
                elif pos.size < 0 and current_price >= self.inds[d]['stop_price']:
                    self.close(data=d)
                    self.inds[d]['entry_bar'] = None
                    self.inds[d]['last_trade_bar'] = len(d)
                    continue

            # Update trailing stop to save profits after a trade
            if pos:
                if pos.size > 0:
                    new_stop_price = current_price - self.params.atr_multiplier * self.inds[d]['atr'][0]
                    if self.inds[d]['stop_price'] is None or new_stop_price > self.inds[d]['stop_price']:
                        self.inds[d]['stop_price'] = new_stop_price
                else:
                    new_stop_price = current_price + self.params.atr_multiplier * self.inds[d]['atr'][0]
                    if self.inds[d]['stop_price'] is None or new_stop_price < self.inds[d]['stop_price']:
                        self.inds[d]['stop_price'] = new_stop_price

            # Leave 1 bar between trades to avoid too rapid of a re-entry
            if self.inds[d]['last_trade_bar'] and (len(d) - self.inds[d]['last_trade_bar']) < self.params.min_gap_bars:
                continue

            # Entry signals
            if not pos:
                price_change = d.close[0] - d.close[-self.params.price_lookback]
                vol_osc_change = self.inds[d]['vol_osc'][0] - self.inds[d]['vol_osc'][-self.params.price_lookback]

                # Position size adjusted for volatility
                pct_atr = self.inds[d]['atr'][0] / current_price
                size_factor = min(0.8, max(0.2, 0.1 / pct_atr)) if pct_atr > 0 else 0.5
                cash = self.broker.getcash()
                size = int(cash * size_factor / current_price)
                if size <= 0:
                    continue

                # Bullish divergence (price up, vol osc down, uptrend, RSI not overbought)
                # Enter long position with ATR stop
                if price_change < 0 < vol_osc_change and current_price > self.inds[d]['sma'][0] and self.inds[d]['rsi'] < 70 and size > 0:
                    self.buy(data=d, size=size)
                    self.inds[d]['entry_bar'] = len(d)
                    self.inds[d]['last_trade_bar'] = len(d)
                    self.inds[d]['stop_price'] = current_price - self.params.atr_multiplier * self.inds[d]['atr'][0]

                # Bearish divergence (price down, vol osc up, downtrend, RSI not oversold)
                # Enter short position with ATR stop
                elif vol_osc_change < 0 < price_change and current_price < self.inds[d]['sma'][0] and self.inds[d]['rsi'] > 30 and size > 0:
                    self.sell(data=d, size=size)
                    self.inds[d]['entry_bar'] = len(d)
                    self.inds[d]['last_trade_bar'] = len(d)
                    self.inds[d]['stop_price'] = current_price + self.params.atr_multiplier * self.inds[d]['atr'][0]

strategies = {
    1: SimpleSMA,
    2: SMACrossover,
    3: MACD,
    4: RSI,
    5: BollingerBands,
    6: VolOscDivergence,
}

def runall(frames, strategy):

    # Create the 1st data
    for i, frame in enumerate(frames):
        # Create a cerebro
        cerebro = bt.Cerebro()

        # Add data frames to cerebro as data feeds
        ticker_name = str(db.tickers[i]) if i < len(db.tickers) else f"Ticker_{i}"
        data_feed = bt.feeds.PandasData(dataname=frame)
        cerebro.adddata(data_feed, name=ticker_name)

        # Add the strategy
        cerebro.addstrategy(strategies[strategy])

        # Add cash
        cerebro.broker.setcash(start_cash)

        # And run it
        print('Starting Portfolio Value: %.2f' % cerebro.broker.getvalue())
        cerebro.run()
        print('Final Portfolio Value: %.2f' % cerebro.broker.getvalue())
        print('Delta cash: %.2f' % (cerebro.broker.getcash() - start_cash))

        # Plot if requested
        cerebro.plot(style='candlestick', numfigs=1)

def runone(ticker, strategy):

    # Create a cerebro
    cerebro = bt.Cerebro()

    # Add data frames to cerebro as data feeds
    frame = db.frames[db.tickers.index(ticker)]
    data_feed = bt.feeds.PandasData(dataname=frame)
    cerebro.adddata(data_feed, name=ticker)

    # Add the strategy
    cerebro.addstrategy(strategies[strategy])

    # Add cash
    cerebro.broker.setcash(start_cash)

    # And run it
    print('Starting Portfolio Value: %.2f' % cerebro.broker.getvalue())
    cerebro.run()
    print('Final Portfolio Value: %.2f' % cerebro.broker.getvalue())
    print('Delta cash: %.2f' % (cerebro.broker.getcash() - start_cash))

    # Plot if requested
    cerebro.plot(style='candlestick', numfigs=1)