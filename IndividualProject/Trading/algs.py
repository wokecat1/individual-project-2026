from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import numpy as np
import backtrader as bt
import backtrader.analyzers as btanalyzers
import pandas as pd

from Database import db
from Trading.new_alg import ProprietaryAlg

start_cash = 10000

class SMACrossover(bt.SignalStrategy):

    """Simpler trading strategy which uses the crossover of a slower and a faster SMA as an indicator"""

    params = dict(  # params taken from maximum average of optimisation data
        pfast=6,    # period for the fast moving average
        pmid=18,    # period for the medium moving average
        pslow=31,   # period for the slow moving average
        max_hold_bars=30,
        min_gap_bars=1,
        max_risk=0.8,
        min_risk=0.2
    )

    def log(self, txt, dt=None, data=None):
        data = data or self.datas[0]
        dt = dt or data.datetime.date(0)
        print(f'{dt.isoformat()}, {txt}')

    def __init__(self):
        self.inds = {}
        for i, d in enumerate(self.datas):
            sma1 = bt.ind.SMA(d, period=self.p.pfast)       # fast moving average
            sma2 = bt.ind.SMA(d, period=self.p.pmid)        # mid moving average
            sma3 = bt.ind.SMA(d, period=self.p.pslow)       # slow moving average
            crossover_fm = bt.ind.CrossOver(sma1, sma2)     # crossover signal 1
            crossover_ms = bt.ind.CrossOver(sma2, sma3)     # crossover signal 2
            self.inds[d] = {
                'sma1': sma1,
                'sma2': sma2,
                'sma3': sma3,
                'crossover_fm': crossover_fm,
                'crossover_ms': crossover_ms,
                'entry_bar': None,
                'last_trade_bar': None,
                'order': None
            }

    def notify_order(self, order):

        d = order.data

        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:

            if order.isbuy():
                self.log(
                    f'BUY EXEC, '
                    f'Price: {order.executed.price:.2f}, '
                    f'Cost: {order.executed.value:.2f}, '
                    f'Comm: {order.executed.comm:.2f}, '
                    f'bar={len(d)}',
                    data=d
                )

            else:
                self.log(
                    f'SELL EXEC, '
                    f'Price: {order.executed.price:.2f}, '
                    f'Cost: {order.executed.value:.2f}, '
                    f'Comm: {order.executed.comm:.2f}, '
                    f'bar={len(d)}',
                    data=d
                )

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('ORDER FAILED', data=d)

        self.inds[d]['order'] = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return

        self.log(
            'OPERATION PROFIT, GROSS %.2f, NET %.2f' %
            (trade.pnl, trade.pnlcomm),
            data=trade.data
        )

    def next(self):
        for i, d in enumerate(self.datas):
            min_period = max(self.p.pfast, self.p.pmid, self.p.pslow)
            if len(d) < min_period: # need enough data for all indicators to be stable
                continue

            current_price = d.close[0]
            ind = self.inds[d]
            sma_fast_slope = (ind['sma1'][0] - ind['sma1'][-3]) / 4  # slope of fast SMA
            sma_slow_slope = (ind['sma3'][0] - ind['sma3'][-3]) / 4  # slope of slow SMA
            pos = self.getposition(d)

            # ---- Active order check ----
            if ind['order']:
                continue

            # ---- Max hold exit ----
            if pos and ind['entry_bar']:  # entry bar
                if (len(d) - ind['entry_bar']) >= self.p.max_hold_bars:
                    self.close(data=d)
                    ind['entry_bar'] = None
                    ind['last_trade_bar'] = len(d)
                    continue

            # ---- Trailing stops ----
            if pos:
                # Long position
                if pos.size > 0 and ind['crossover_fm'][0] < 0 and sma_slow_slope < 0: # close if MAs cross downwards and slow SMA is negative
                    self.close(data=d)
                    ind['entry_bar'] = None
                    ind['last_trade_bar'] = len(d)
                    continue

                # Short position
                elif pos.size < 0 and ind['crossover_fm'][0] > 0 and sma_slow_slope > 0: # close if MAs cross upwards and slow SMA is positive
                    self.close(data=d)
                    ind['entry_bar'] = None
                    ind['last_trade_bar'] = len(d)
                    continue

            # ---- Position sizing ----
            sma_angle = abs((sma_slow_slope - sma_fast_slope) / (1 + sma_slow_slope * sma_fast_slope))  # angle between slopes
            trend_strength = np.arctan(sma_angle) / (np.pi / 2)                                         # 0 when slopes are parallel, 1 when perpendicular
            size_factor = min(self.p.max_risk, max(self.p.min_risk, trend_strength))                      # trend strength clipped between 0.2 and 0.8
            cash = self.broker.getcash()
            size = int(cash * size_factor / current_price)                                              # number of shares buyable with capital being risked
            if size <= 0:
                continue

            # ---- Entry conditions ----
            if not pos:
                if (ind['crossover_fm'] > 0 and sma_slow_slope > 0 or
                    ind['crossover_ms'] > 0 and sma_fast_slope > 0):  # if MAs cross to upside and slow SMA is positive

                    order = self.buy(data=d, size=size)
                    if order:
                        ind['order'] = order
                        self.log(
                            f'BUY CREATE, {current_price:.2f}, bar={len(d)}',
                            data=d
                        )
                    ind['entry_bar'] = len(d)
                    ind['last_trade_bar'] = len(d)

                elif (ind['crossover_fm'] < 0 and sma_slow_slope < 0 or
                      ind['crossover_ms'] < 0 and sma_fast_slope < 0): # if MAs cross to downside and slow SMA is negative

                    order = self.sell(data=d, size=size)
                    if order:
                        ind['order'] = order
                        self.log(
                            f'SELL CREATE, {current_price:.2f}, bar={len(d)}',
                            data=d
                        )
                    ind['entry_bar'] = len(d)
                    ind['last_trade_bar'] = len(d)

class AdaptiveSMA(bt.Indicator):

    """Custom indicator calculating SMA values with volatility-based adaptive windows"""

    lines = ('sma',)
    params = dict(
        base_period=20,
        vol_period=7,
        vol_factor=1.5,
        min_period=5,
        max_period=40,
    )

    def __init__(self):

        self.vol = bt.ind.StdDev(bt.ind.PctChange(self.data), period=self.p.vol_period)  # Volatility = std dev of percentage price change
        self.vol_hist = []                                                       # Volatility history of stock

    def next(self):

        if len(self.data) < self.p.max_period:
            self.lines.sma[0] = self.data[0]
            return

        current_vol = self.vol[0]

        # Store current volume if it is not NaN
        if not np.isnan(current_vol):
            self.vol_hist.append(current_vol)

        # Determine adaptive period
        if len(self.vol_hist) >= self.p.vol_period:
            avg_vol = np.mean(self.vol_hist[-self.p.vol_period:])

            if avg_vol > 0:
                vol_ratio = current_vol / avg_vol
                denom = 1 + (vol_ratio - 1) * self.p.vol_factor     # Calculate new period: higher vol_ratio -> shorter period
                if denom <= 0:
                    period = self.p.min_period                      # Guarding against divide-by-zero errors
                else:
                    period = int(self.p.base_period / denom)
                period = max(self.p.min_period, min(self.p.max_period, period)) # Clamp period within min and max bounds
            else:
                period = self.p.base_period     # If avg_vol is 0 or current_vol is NaN, revert to base period
        else:
            period = self.p.base_period         # Not enough data, use base period

        # Manually calculate SMA for adaptive period; backtrader built in SMA doesn't allow period to be dynamically changed
        if len(self.data) >= period:
            sma = sum(self.data[-(i + 1)] for i in range(period)) / period
            self.lines.sma[0] = sma
        else:
            self.lines.sma[0] = self.data[0] # If not enough data for the current adaptive period, set to current close

class AdaptiveMAC(bt.Strategy):

    """Trading strategy using crossovers between moving averages whose windows flex depending on market volatility"""

    params = dict( # params taken from maximum average of optimisation data
        fast_base=5,
        slow_base=21,
        min_period_fast=5,
        max_period_fast=25,
        min_period_slow=15,
        max_period_slow=40,
        vol_period=7,
        vol_factor=1.5,
        atr_window=14,
        atr_multiplier=2,
        max_hold_bars=30,
        min_gap_bars=1,
        max_risk=0.8,
        min_risk=0.2,
        trend_smooth_period=3
    )

    def log(self, txt, dt=None, data=None):
        data = data or self.datas[0]
        dt = dt or data.datetime.date(0)
        print(f'{dt.isoformat()}, {txt}')

    def __init__(self):
        self.inds = {}
        for d in self.datas:
            fast_ma = AdaptiveSMA(
                d,
                base_period=self.p.fast_base,
                vol_period=self.p.vol_period,
                vol_factor=self.p.vol_factor,
                min_period=self.p.min_period_fast,
                max_period=self.p.max_period_fast
            )
            slow_ma = AdaptiveSMA(
                d,
                base_period=self.p.slow_base,
                vol_period=self.p.vol_period,
                vol_factor=self.p.vol_factor,
                min_period=self.p.min_period_slow,
                max_period=self.p.max_period_slow
            )
            crossover = bt.ind.CrossOver(slow_ma, fast_ma) # indicator to detect when fast_ma and slow_ma cross
            atr = bt.ind.ATR(d, period=14)

            self.inds[d] = dict(
                fast_ma=fast_ma,
                slow_ma=slow_ma,
                crossover=crossover,
                atr=atr,
                entry_bar=None,
                last_trade_bar=None,
                stop_price=None,
                order=None
            )

    def notify_order(self, order):

        d = order.data

        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:

            if order.isbuy():
                self.log(
                    f'BUY EXEC, '
                    f'Price: {order.executed.price:.2f}, '
                    f'Cost: {order.executed.value:.2f}, '
                    f'Comm: {order.executed.comm:.2f}, '
                    f'bar={len(d)}',
                    data=d
                )

            else:
                self.log(
                    f'SELL EXEC, '
                    f'Price: {order.executed.price:.2f}, '
                    f'Cost: {order.executed.value:.2f}, '
                    f'Comm: {order.executed.comm:.2f}, '
                    f'bar={len(d)}',
                    data=d
                )

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('ORDER FAILED', data=d)

        self.inds[d]['order'] = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return

        self.log(
            'OPERATION PROFIT, GROSS %.2f, NET %.2f' %
            (trade.pnl, trade.pnlcomm),
            data=trade.data
        )

    def next(self):
        for d in self.datas:
            if len(d) < max(self.p.max_period_slow, 4):
                continue

            current_price = d.close[0]
            ind = self.inds[d]
            pos = self.getposition(d)
            crossover = ind['crossover'][0]
            fast_ma =ind['fast_ma']
            slow_ma =  ind['slow_ma']
            atr = ind['atr'][0]

            # ---- Active order check ----
            if ind['order']:
                continue

            # ---- Max hold exit ----
            if pos and ind['entry_bar'] is not None:
                if len(d) - ind['entry_bar'] >= self.p.max_hold_bars:
                    self.close(data=d)
                    ind['entry_bar'] = None
                    ind['stop_price'] = None
                    ind['last_trade_bar'] = len(d)
                    continue

            # ---- Position management ----
            if pos:

                # Opposite crossover check
                if (pos.size > 0 and crossover < 0) or \
                        (pos.size < 0 and crossover > 0):
                    self.close(data=d)
                    ind['entry_bar'] = None
                    ind['stop_price'] = None
                    ind['last_trade_bar'] = len(d)
                    continue

                if pos.size > 0:
                    new_stop = current_price - self.p.atr_multiplier * atr
                    if ind['stop_price'] is None or new_stop > ind['stop_price']:
                        ind['stop_price'] = new_stop
                else:
                    new_stop = current_price + self.p.atr_multiplier * atr
                    if ind['stop_price'] is None or new_stop < ind['stop_price']:
                        ind['stop_price'] = new_stop

                # Stop execution
                if ind['stop_price'] is not None and (
                        (pos.size > 0 and current_price < ind['stop_price']) or
                        (pos.size < 0 and current_price > ind['stop_price'])
                ):
                    self.close(data=d)
                    ind['entry_bar'] = None
                    ind['stop_price'] = None
                    ind['last_trade_bar'] = len(d)
                    continue

            # ---- Trade minimum gap control ----
            if ind['last_trade_bar'] is not None and \
                    len(d) - ind['last_trade_bar'] < self.p.min_gap_bars:
                continue

            # ---- Trade sizing based on angle between MA slopes ----
            fast_ma_slope = (fast_ma[0] - fast_ma[-self.p.trend_smooth_period]) / (self.p.trend_smooth_period + 1)
            slow_ma_slope = (slow_ma[0] - slow_ma[-self.p.trend_smooth_period]) / (self.p.trend_smooth_period + 1)
            sma_angle = abs(
                (slow_ma_slope - fast_ma_slope) / (1 + slow_ma_slope * fast_ma_slope))  # angle between slopes
            trend_strength = np.arctan(sma_angle) / (np.pi / 2)  # 0 when slopes are parallel, 1 when perpendicular
            size_factor = min(self.p.max_risk,
                              max(self.p.min_risk, trend_strength))  # trend strength clipped between 0.2 and 0.8

            atr_pct = atr / current_price
            if atr_pct > 0:                              # risk smoothing using ATR
                size_factor *= min(1, 0.1 / atr_pct)

            cash = self.broker.getcash()
            size = int(cash * size_factor / current_price)  # number of shares buyable with capital being risked
            if size <= 0:
                continue

            # ---- Entry conditions ----
            if not pos:
                if crossover > 0:
                    order = self.buy(data=d, size=size)
                    if order:
                        ind['order'] = order
                        self.log(
                            f'BUY CREATE, {current_price:.2f}, bar={len(d)}',
                            data=d
                        )
                    ind['entry_bar'] = len(d)
                    ind['last_trade_bar'] = len(d)
                    ind['stop_price'] = current_price - self.p.atr_multiplier * atr

                elif crossover < 0:
                    order = self.sell(data=d, size=size)
                    if order:
                        ind['order'] = order
                        self.log(
                            f'SELL CREATE, {current_price:.2f}, bar={len(d)}',
                            data=d
                        )
                    ind['entry_bar'] = len(d)
                    ind['last_trade_bar'] = len(d)
                    ind['stop_price'] = current_price + self.p.atr_multiplier * atr

class MACD(bt.Strategy):

    """Trading strategy using a Moving Average Convergence/Divergence indicator"""

    params = dict( # params taken from maximum average of optimisation data
        fast_period=12,         # period for fast MA
        slow_period=40,         # period for slow MA
        sig_period=13,           # period for MACD signal
        atr_period=14,          # ATR period for stops
        atr_multiplier=2.0,     # ATR value scalar
        max_hold_bars=30,
        min_gap_bars=1,
        max_risk=0.8,
        min_risk=0.2,
        trend_smooth_period=3,  # bars to compute slope for trend strength
    )

    def log(self, txt, dt=None, data=None):
        data = data or self.datas[0]
        dt = dt or data.datetime.date(0)
        print(f'{dt.isoformat()}, {txt}')

    def __init__(self):
        self.inds = {}
        for d in self.datas:
            macd = bt.ind.MACD(
                d.close,
                period_me1=self.p.fast_period,
                period_me2=self.p.slow_period,
                period_signal=self.p.sig_period
            )
            crossover = bt.ind.CrossOver(macd.macd, macd.signal)
            atr = bt.ind.ATR(d, period=self.p.atr_period)

            self.inds[d] = dict(
                macd=macd,
                crossover=crossover,
                atr=atr,
                entry_bar=None,
                last_trade_bar=None,
                stop_price=None,
                order=None
            )

    def notify_order(self, order):

        d = order.data

        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:

            if order.isbuy():
                self.log(
                    f'BUY EXEC, '
                    f'Price: {order.executed.price:.2f}, '
                    f'Cost: {order.executed.value:.2f}, '
                    f'Comm: {order.executed.comm:.2f}, '
                    f'bar={len(d)}',
                    data=d
                )

            else:
                self.log(
                    f'SELL EXEC, '
                    f'Price: {order.executed.price:.2f}, '
                    f'Cost: {order.executed.value:.2f}, '
                    f'Comm: {order.executed.comm:.2f}, '
                    f'bar={len(d)}',
                    data=d
                )

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('ORDER FAILED', data=d)

        self.inds[d]['order'] = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return

        self.log(
            'OPERATION PROFIT, GROSS %.2f, NET %.2f' %
            (trade.pnl, trade.pnlcomm),
            data=trade.data
        )

    def next(self):
        for d in self.datas:
            if len(d) < max(self.p.slow_period, self.p.atr_period, self.p.trend_smooth_period):
                continue

            current_price = d.close[0]
            ind = self.inds[d]
            pos = self.getposition(d)
            atr_val = ind['atr'][0]
            crossover = ind['crossover'][0]
            macd_line = ind['macd'].macd

            # ---- Active order check ----
            if ind['order']:
                continue

            # ---- Max hold exit ----
            if pos and ind['entry_bar'] is not None:
                if len(d) - ind['entry_bar'] >= self.p.max_hold_bars:
                    self.close(data=d)
                    ind['entry_bar'] = None
                    ind['stop_price'] = None
                    ind['last_trade_bar'] = len(d)
                    continue

            # ---- Opposite crossover dominates exit ----
            if pos:
                if (pos.size > 0 and crossover < 0) or (pos.size < 0 and crossover > 0):
                    self.close(data=d)
                    ind['entry_bar'] = None
                    ind['stop_price'] = None
                    ind['last_trade_bar'] = len(d)
                    continue

            # ---- ATR trailing stop update ----
            if pos:
                if pos.size > 0:
                    new_stop = current_price - self.p.atr_multiplier * atr_val
                    if ind['stop_price'] is None or new_stop > ind['stop_price']:
                        ind['stop_price'] = new_stop
                else:
                    new_stop = current_price + self.p.atr_multiplier * atr_val
                    if ind['stop_price'] is None or new_stop < ind['stop_price']:
                        ind['stop_price'] = new_stop

                # Execute stop
                if ind['stop_price'] is not None and (
                        (pos.size > 0 and current_price <= ind['stop_price']) or
                        (pos.size < 0 and current_price >= ind['stop_price'])
                ):
                    self.close(data=d)
                    ind['entry_bar'] = None
                    ind['stop_price'] = None
                    ind['last_trade_bar'] = len(d)
                    continue

            # ---- Trade minimum gap control ----
            if ind['last_trade_bar'] is not None and len(d) - ind['last_trade_bar'] < self.p.min_gap_bars:
                continue

            # ---- Position sizing (ATR + trend-strength adjusted) ----
            macd_slope = (macd_line[0] - macd_line[-self.p.trend_smooth_period]) / (self.p.trend_smooth_period + 1)
            trend_strength = min(1.0, abs(macd_slope) / max(abs(macd_line[-self.p.trend_smooth_period]), 1e-6))
            trend_factor = min(self.p.max_risk, max(self.p.min_risk, trend_strength)) # Clip between min_risk and max_risk

            atr_pct = atr_val / current_price
            if atr_pct > 0:
                size_factor = trend_factor * min(1.0, 0.1 / atr_pct)
            else:
                size_factor = trend_factor

            cash = self.broker.getcash()
            size = int(cash * size_factor / current_price)
            if size <= 0:
                continue

            # ---- Entry conditions ----
            if not pos:
                if crossover > 0:  # MACD bullish crossover
                    order = self.buy(data=d, size=size)
                    if order:
                        ind['order'] = order
                        self.log(
                            f'BUY CREATE, {current_price:.2f}, bar={len(d)}',
                            data=d
                        )
                    ind['entry_bar'] = len(d)
                    ind['stop_price'] = current_price - self.p.atr_multiplier * atr_val
                    ind['last_trade_bar'] = len(d)

                elif crossover < 0:  # MACD bearish crossover
                    order = self.sell(data=d, size=size)
                    if order:
                        ind['order'] = order
                        self.log(
                            f'SELL CREATE, {current_price:.2f}, bar={len(d)}',
                            data=d
                        )
                    ind['entry_bar'] = len(d)
                    ind['stop_price'] = current_price + self.p.atr_multiplier * atr_val
                    ind['last_trade_bar'] = len(d)

class RSI(bt.Strategy):

    """RSI strategy with ATR trailing stops and trend-strength sizing"""

    params = dict( # params taken from maximum average of optimisation data
        period=11,          # RSI period
        overbought=70,      # overbought threshold
        oversold=35,        # oversold threshold
        atr_period=14,      # ATR period for trailing stop
        atr_multiplier=1.5, # ATR multiplier for trailing stop
        stop_smooth=0.2,    # smoothing factor for ATR trailing stop
        max_hold_bars=30,
        min_gap_bars=1,
        max_risk=0.8,
        min_risk=0.2,
        trend_smooth_period=3
    )

    def log(self, txt, dt=None, data=None):
        data = data or self.datas[0]
        dt = dt or data.datetime.date(0)
        print(f'{dt.isoformat()}, {txt}')

    def __init__(self):
        self.inds = {}
        for d in self.datas:
            rsi = bt.ind.RSI(d.close, period=self.p.period)
            atr = bt.ind.ATR(d, period=self.p.atr_period)

            self.inds[d] = dict(
                rsi=rsi,
                atr=atr,
                entry_bar=None,
                last_trade_bar=None,
                stop_price=None,
                order=None
            )

    def notify_order(self, order):

        d = order.data

        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:

            if order.isbuy():
                self.log(
                    f'BUY EXEC, '
                    f'Price: {order.executed.price:.2f}, '
                    f'Cost: {order.executed.value:.2f}, '
                    f'Comm: {order.executed.comm:.2f}, '
                    f'bar={len(d)}',
                    data=d
                )

            else:
                self.log(
                    f'SELL EXEC, '
                    f'Price: {order.executed.price:.2f}, '
                    f'Cost: {order.executed.value:.2f}, '
                    f'Comm: {order.executed.comm:.2f}, '
                    f'bar={len(d)}',
                    data=d
                )

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('ORDER FAILED', data=d)

        self.inds[d]['order'] = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return

        self.log(
            'OPERATION PROFIT, GROSS %.2f, NET %.2f' %
            (trade.pnl, trade.pnlcomm),
            data=trade.data
        )

    def next(self):
        for d in self.datas:
            if len(d) < max(self.p.period, self.p.atr_period, self.p.trend_smooth_period):
                continue

            current_price = d.close[0]
            ind = self.inds[d]
            pos = self.getposition(d)
            current_rsi = ind['rsi'][0]
            atr_val = ind['atr'][0]

            # ---- Active order check ----
            if ind['order']:
                continue

            # ---- Max hold exit ----
            if pos and ind['entry_bar'] is not None:
                if len(d) - ind['entry_bar'] >= self.p.max_hold_bars:
                    self.close(data=d)
                    ind['entry_bar'] = None
                    ind['stop_price'] = None
                    ind['last_trade_bar'] = len(d)
                    continue

            # ---- Opposite extreme dominates exit ----
            if pos:
                if (pos.size > 0 and current_rsi > self.p.overbought) or \
                   (pos.size < 0 and current_rsi < self.p.oversold):
                    self.close(data=d)
                    ind['entry_bar'] = None
                    ind['stop_price'] = None
                    ind['last_trade_bar'] = len(d)
                    continue

            # ---- ATR trailing stop ----
                # Long position
                if pos.size > 0:
                    target_stop = current_price - self.p.atr_multiplier * atr_val
                    if ind['stop_price'] is None:
                        ind['stop_price'] = target_stop
                    else:
                        # move stop gradually upward, smoothing factor applied
                        ind['stop_price'] = ind['stop_price'] + self.p.stop_smooth * (target_stop - ind['stop_price'])

                    if current_price <= ind['stop_price']:
                        self.close(data=d)
                        ind['entry_bar'] = None
                        ind['stop_price'] = None
                        ind['last_trade_bar'] = len(d)
                        continue

                # Short position
                else:
                    target_stop = current_price + self.p.atr_multiplier * atr_val
                    if ind['stop_price'] is None:
                        ind['stop_price'] = target_stop
                    else:
                        # move stop gradually downward, smoothing factor applied
                        ind['stop_price'] = ind['stop_price'] + self.p.stop_smooth * (target_stop - ind['stop_price'])

                    if current_price >= ind['stop_price']:
                        self.close(data=d)
                        ind['entry_bar'] = None
                        ind['stop_price'] = None
                        ind['last_trade_bar'] = len(d)
                        continue

            # ---- Minimum trade gap control ----
            if ind['last_trade_bar'] is not None and len(d) - ind['last_trade_bar'] < self.p.min_gap_bars:
                continue

            # ---- Position sizing ----
            rsi_slope = (ind['rsi'][0] - ind['rsi'][-self.p.trend_smooth_period]) / ind['rsi'][0]
            trend_strength = min(1.0, abs(rsi_slope))   # Compute RSI slope for trend strength
            trend_factor = min(self.p.max_risk, max(self.p.min_risk, trend_strength))

            atr_pct = atr_val / current_price
            if atr_pct > 0:
                size_factor = trend_factor * min(1.0, 0.1 / atr_pct)
            else:
                size_factor = trend_factor

            cash = self.broker.getcash()
            size = int(cash * size_factor / current_price)
            if size <= 0:
                continue

            # ---- Entry conditions ----
            if not pos:
                if current_rsi < self.p.oversold and rsi_slope > 0:  # RSI rising from oversold
                    order = self.buy(data=d, size=size)
                    if order:
                        ind['order'] = order
                        self.log(
                            f'BUY CREATE, {current_price:.2f}, bar={len(d)}',
                            data=d
                        )
                    ind['entry_bar'] = len(d)
                    ind['stop_price'] = current_price - self.p.atr_multiplier * atr_val
                    ind['last_trade_bar'] = len(d)

                elif current_rsi > self.p.overbought and rsi_slope < 0:  # RSI falling from overbought
                    order = self.sell(data=d, size=size)
                    if order:
                        ind['order'] = order
                        self.log(
                            f'SELL CREATE, {current_price:.2f}, bar={len(d)}',
                            data=d
                        )
                    ind['entry_bar'] = len(d)
                    ind['stop_price'] = current_price + self.p.atr_multiplier * atr_val
                    ind['last_trade_bar'] = len(d)

class BollingerBands(bt.Strategy):

    """Bollinger Bands strategy with ATR trailing stops, volatility-adjusted sizing, and trend strength scaling"""

    params = dict( # params taken from maximum average of optimisation data
        period=7,
        devfactor=2,
        mult_factor=0.1,
        atr_window=14,
        atr_multiplier=2,
        stop_smooth=0.2,
        max_hold_bars=30,
        min_gap_bars=1,
        max_risk=0.8,
        min_risk=0.2
    )

    def log(self, txt, dt=None, data=None):
        data = data or self.datas[0]
        dt = dt or data.datetime.date(0)
        print(f'{dt.isoformat()}, {txt}')

    def __init__(self):
        self.inds = {}
        self.buyprice = None
        self.buycomm = None

        for d in self.datas:
            bands = bt.ind.BollingerBands(d.close, period=self.p.period, devfactor=self.p.devfactor)
            atr = bt.ind.ATR(d, period=self.p.atr_window)

            self.inds[d] = dict(
                bands=bands,
                upper=bands.top,
                middle=bands.mid,
                lower=bands.bot,
                atr=atr,
                entry_bar=None,
                last_trade_bar=None,
                stop_price=None,
                order=None
            )

    def notify_order(self, order):

        d = order.data

        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:

            if order.isbuy():
                self.log(
                    f'BUY EXEC, '
                    f'Price: {order.executed.price:.2f}, '
                    f'Cost: {order.executed.value:.2f}, '
                    f'Comm: {order.executed.comm:.2f}, '
                    f'bar={len(d)}',
                    data=d
                )

            else:
                self.log(
                    f'SELL EXEC, '
                    f'Price: {order.executed.price:.2f}, '
                    f'Cost: {order.executed.value:.2f}, '
                    f'Comm: {order.executed.comm:.2f}, '
                    f'bar={len(d)}',
                    data=d
                )

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('ORDER FAILED', data=d)

        self.inds[d]['order'] = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return

        self.log(
            'OPERATION PROFIT, GROSS %.2f, NET %.2f' %
            (trade.pnl, trade.pnlcomm),
            data=trade.data
        )

    def next(self):
        for d in self.datas:
            if len(d) < max(self.p.period, self.p.atr_window):
                continue

            current_price = d.close[0]
            ind = self.inds[d]
            pos = self.getposition(d)
            upper = ind['upper'][0]
            middle = ind['middle'][0]
            lower = ind['lower'][0]
            atr_val = ind['atr'][0]
            bandwidth = (upper - lower) / middle

            # ---- Active order check ----
            if ind['order']:
                continue

            # ---- Trade only in high volatility ----
            if bandwidth < 0.02:
                continue

            # ---- Max hold exit ----
            if pos and ind['entry_bar'] is not None:
                if len(d) - ind['entry_bar'] >= self.p.max_hold_bars:
                    self.close(data=d)
                    ind['entry_bar'] = None
                    ind['stop_price'] = None
                    ind['last_trade_bar'] = len(d)
                    continue

            # ---- Position management ----
            if pos:
                if pos.size > 0 and current_price < ind['stop_price']: # long position, price below lower band
                    self.close(data=d)
                    ind['entry_bar'] = None
                    ind['stop_price'] = None
                    ind['last_trade_bar'] = len(d)
                    continue
                elif pos.size < 0 and current_price > ind['stop_price']: # short position, price above upper band
                    self.close(data=d)
                    ind['entry_bar'] = None
                    ind['stop_price'] = None
                    ind['last_trade_bar'] = len(d)
                    continue

                # ATR trailing stop
                if pos.size > 0:
                    new_stop = current_price + atr_val * self.p.atr_multiplier
                    if ind['stop_price'] is None:
                        ind['stop_price'] = new_stop
                    else:
                        ind['stop_price'] += self.p.stop_smooth * (new_stop - ind['stop_price'])
                    if current_price <= ind['stop_price']:
                        self.close(data=d)
                        ind['entry_bar'] = None
                        ind['stop_price'] = None
                        ind['last_trade_bar'] = len(d)
                        continue

                else:
                    new_stop = current_price - atr_val * self.p.atr_multiplier
                    if ind['stop_price'] is None:
                        ind['stop_price'] = new_stop
                    else:
                        ind['stop_price'] += self.p.stop_smooth * (new_stop - ind['stop_price'])
                    if current_price >= ind['stop_price']:
                        self.close(data=d)
                        ind['entry_bar'] = None
                        ind['stop_price'] = None
                        ind['last_trade_bar'] = len(d)
                        continue

            # ---- Minimum gap control ----
            if ind['last_trade_bar'] is not None and (len(d) - ind['last_trade_bar']) < self.p.min_gap_bars:
                continue

            # ---- Position sizing ----
            if upper != lower:
                trend_strength = 1 - abs((current_price - middle) / (upper - lower))
            else:
                trend_strength = 0.5
            trend_strength = min(1.0, max(0.0, trend_strength))

            atr_pct = atr_val / current_price
            if atr_pct > 0:
                base_size_factor = min(self.p.max_risk, max(self.p.min_risk, 0.1 / atr_pct))
            else:
                base_size_factor = 0.5

            size_factor = base_size_factor * trend_strength
            size_factor = min(self.p.max_risk, max(self.p.min_risk, size_factor))

            cash = self.broker.getcash()
            size = int(cash * size_factor / current_price)
            if size <= 0:
                continue

            # ---- Entry conditions ----
            if not pos:
                if d.close[-1] <= upper and current_price > upper: # current price too low
                    order = self.buy(data=d, size=size)
                    if order:
                        ind['order'] = order
                        self.log(
                            f'BUY CREATE, {current_price:.2f}, bar={len(d)}',
                            data=d
                        )
                    ind['entry_bar'] = len(d)
                    ind['stop_price'] = current_price - self.p.atr_multiplier * atr_val
                    ind['last_trade_bar'] = len(d)

                elif d.close[-1] >= lower and current_price < lower: # current price too high
                    order = self.sell(data=d, size=size)
                    if order:
                        ind['order'] = order
                        self.log(
                            f'SELL CREATE, {current_price:.2f}, bar={len(d)}',
                            data=d
                        )
                    ind['entry_bar'] = len(d)
                    ind['stop_price'] = current_price + self.p.atr_multiplier * atr_val
                    ind['last_trade_bar'] = len(d)

class VolOscDivergence(bt.Strategy):

    """Volume Oscillator Divergence strategy with ATR trailing stops and volatility-adjusted sizing"""

    params = dict( # params taken from maximum average of optimisation data
        vol_window=20,
        vol_roc_period=9,
        price_lookback=7,
        sma_window=28,
        atr_window=14,
        atr_multiplier=2,
        rsi_window=18,
        max_hold_bars=30,
        min_gap_bars=1,
        max_risk=0.8,
        min_risk=0.2,
        stop_smooth=0.2
    )

    def log(self, txt, dt=None, data=None):
        data = data or self.datas[0]
        dt = dt or data.datetime.date(0)
        print(f'{dt.isoformat()}, {txt}')

    def __init__(self):
        self.inds = {}
        self.buyprice = None
        self.buycomm = None

        for i, d in enumerate(self.datas):

            returns = bt.ind.PctChange(d.close, period=1)
            vol = bt.ind.StdDev(returns, period=self.p.vol_window)
            vol_osc = bt.ind.ROC(vol, period=self.p.vol_roc_period)
            sma = bt.ind.SMA(d.close, period=self.p.sma_window)
            atr = bt.ind.ATR(d, period=self.p.atr_window)
            rsi = bt.ind.RSI(d.close, period=self.p.rsi_window)

            self.inds[d] = dict(
                returns=returns,
                vol=vol,
                vol_osc=vol_osc,
                sma=sma,
                atr=atr,
                rsi=rsi,
                entry_bar=None,
                last_trade_bar=None,
                stop_price=None,
                order=None
            )

    def notify_order(self, order):

        d = order.data

        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:

            if order.isbuy():
                self.log(
                    f'BUY EXEC, '
                    f'Price: {order.executed.price:.2f}, '
                    f'Cost: {order.executed.value:.2f}, '
                    f'Comm: {order.executed.comm:.2f}, '
                    f'bar={len(d)}',
                    data=d
                )

            else:
                self.log(
                    f'SELL EXEC, '
                    f'Price: {order.executed.price:.2f}, '
                    f'Cost: {order.executed.value:.2f}, '
                    f'Comm: {order.executed.comm:.2f}, '
                    f'bar={len(d)}',
                    data=d
                )

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('ORDER FAILED', data=d)

        self.inds[d]['order'] = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return

        self.log(
            'OPERATION PROFIT, GROSS %.2f, NET %.2f' %
            (trade.pnl, trade.pnlcomm),
            data=trade.data
        )

    def next(self):
        for d in self.datas:
            min_period = max(
                self.p.vol_window + self.p.vol_roc_period,
                self.p.price_lookback,
                self.p.sma_window,
                self.p.atr_window,
                self.p.rsi_window
            )
            if len(d) < min_period:
                continue

            current_price = d.close[0]
            ind = self.inds[d]
            pos = self.getposition(d)
            atr = ind['atr'][0]
            sma = ind['sma'][0]
            rsi = ind['rsi'][0]
            vol_osc = ind['vol_osc'][0]

            # ---- Active order check ----
            if ind['order']:
                continue

            # ---- Max hold exit ----
            if pos and ind['entry_bar'] is not None:
                if len(d) - ind['entry_bar'] >= self.p.max_hold_bars:
                    self.close(data=d)
                    ind['entry_bar'] = None
                    ind['stop_price'] = None
                    ind['last_trade_bar'] = len(d)
                    continue

            # ---- Position management ----
            if pos:
                if ind['stop_price'] is not None:
                    # Long positions: exit if price falls below stop (current_price - (3 * ATR))
                    if pos.size > 0 and current_price <= ind['stop_price']:
                        self.close(data=d)
                        ind['entry_bar'] = None
                        ind['last_trade_bar'] = len(d)
                        ind['stop_price'] = None
                        continue

                    # Short positions: exit if price rises above stop (current_price + (3 * ATR))
                    elif pos.size < 0 and current_price >= ind['stop_price']:
                        self.close(data=d)
                        ind['entry_bar'] = None
                        ind['last_trade_bar'] = len(d)
                        ind['stop_price'] = None
                        continue

                # ATR trailing stop
                if pos.size > 0:
                    target_stop = current_price - self.p.atr_multiplier * atr
                    if ind['stop_price'] is None:
                        ind['stop_price'] = target_stop
                    else:
                        # apply smoothing
                        ind['stop_price'] += self.p.stop_smooth * (target_stop - ind['stop_price'])
                    if current_price <= ind['stop_price']:
                        self.close(data=d)
                        ind['entry_bar'] = None
                        ind['stop_price'] = None
                        ind['last_trade_bar'] = len(d)
                        continue

                else:
                    target_stop = current_price + self.p.atr_multiplier * atr
                    if ind['stop_price'] is None:
                        ind['stop_price'] = target_stop
                    else:
                        ind['stop_price'] += self.p.stop_smooth * (target_stop - ind['stop_price'])
                    if current_price >= ind['stop_price']:
                        self.close(data=d)
                        ind['entry_bar'] = None
                        ind['stop_price'] = None
                        ind['last_trade_bar'] = len(d)
                        continue

            # ---- Minimum gap control ----
            if ind['last_trade_bar'] is not None and (len(d) - ind['last_trade_bar']) < self.p.min_gap_bars:
                continue

            # ---- Trend & volatility adjusted sizing ----
            price_change = current_price - d.close[-self.p.price_lookback]
            vol_osc_change = vol_osc - ind['vol_osc'][-self.p.price_lookback]

            # trend strength factor (price vs SMA)
            trend_strength = abs(current_price - sma) / sma
            trend_strength = min(1.0, max(0.0, trend_strength))

            pct_atr = atr / current_price
            if pct_atr > 0:
                base_size_factor = min(self.p.max_risk, max(self.p.min_risk, 0.1 / pct_atr))
            else:
                base_size_factor = 0.5

            size_factor = base_size_factor * trend_strength
            size_factor = min(self.p.max_risk, max(self.p.min_risk, size_factor))
            cash = self.broker.getcash()
            size = int(cash * size_factor / current_price)
            if size <= 0:
                continue

            # ---- Entry signals ----
            if not pos:
                # Bullish divergence
                if price_change < 0 < vol_osc_change and current_price > sma and rsi < 70:
                    order = self.buy(data=d, size=size)
                    if order:
                        ind['order'] = order
                        self.log(
                            f'BUY CREATE, {current_price:.2f}, bar={len(d)}',
                            data=d
                        )
                    ind['entry_bar'] = len(d)
                    ind['last_trade_bar'] = len(d)
                    ind['stop_price'] = current_price - self.p.atr_multiplier * atr

                # Bearish divergence
                elif price_change > 0 > vol_osc_change and current_price < sma and rsi > 30:
                    order = self.sell(data=d, size=size)
                    if order:
                        ind['order'] = order
                        self.log(
                            f'SELL CREATE, {current_price:.2f}, bar={len(d)}',
                            data=d
                        )
                    ind['entry_bar'] = len(d)
                    ind['last_trade_bar'] = len(d)
                    ind['stop_price'] = current_price + self.p.atr_multiplier * atr

strategies = {
    1: SMACrossover,
    2: AdaptiveMAC,
    3: MACD,
    4: RSI,
    5: BollingerBands,
    6: VolOscDivergence,
    7: ProprietaryAlg,
}

def runall(sim, frames, strategy):

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

        # Add cash and commission (0.1%)
        cerebro.broker.setcash(start_cash)
        cerebro.broker.setcommission(commission=0.001)

        # And run it
        print(cerebro.broker.getvalue())
        cerebro.run()
        print(cerebro.broker.getvalue())
        cerebro.broker.setcash(start_cash)

        # Plot if requested
        cerebro.plot(style='candlestick', numfigs=1)

def runone(sim, ticker, frames, strategy):

    # Create a cerebro
    cerebro = bt.Cerebro()

    # Add data frames to cerebro as data feeds
    frame = frames[db.tickers.index(ticker)]
    data_feed = bt.feeds.PandasData(dataname=frame)
    cerebro.adddata(data_feed, name=ticker)

    # Add the strategy
    # cerebro.addstrategy(strategies[strategy])

    # Add cash and commission (0.1%)
    cerebro.broker.setcash(start_cash)
    cerebro.broker.setcommission(commission=0.001)

    # Add analyzers
    cerebro.addanalyzer(btanalyzers.SharpeRatio, _name="sharpe")
    cerebro.addanalyzer(btanalyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(btanalyzers.Returns, _name="returns")

    # Optimise strategy
    cerebro.optstrategy(ProprietaryAlg,
                        vol_window=range(20, 36, 5),
                        vol_roc_period=range(7, 12, 2),
                        price_lookback=range(7, 12, 2),
                        fast_period=range(7, 15, 3),
                        slow_period=range(21, 41, 5),
                        sig_period=range(7, 15, 2)
                        )
    '''cerebro.optstrategy(SMACrossover,
                        pfast=range(3, 8),
                        pmid=range(10, 21),
                        pslow=range(21, 41))

    cerebro.optstrategy(AdaptiveMAC,
                        fast_base=range(5, 16, 5),
                        slow_base=range(14, 29, 7),
                        min_period_fast=range(2, 6),
                        max_period_fast=range(10, 21, 5),
                        min_period_slow=range(10, 26, 5),
                        max_period_slow=range(25, 46, 5))

    cerebro.optstrategy(MACD,
                        fast_period=range(7, 15),
                        slow_period=range(21, 41),
                        sig_period=range(7, 15))

    cerebro.optstrategy(RSI,
                        period=range(7, 29),
                        overbought=range(55, 71, 5),
                        oversold=range(30, 41, 5))

     cerebro.optstrategy(BollingerBands, period=range(7, 29))

    cerebro.optstrategy(VolOscDivergence,
                        vol_window=range(15, 36, 5),
                        vol_roc_period=range(3, 11),
                        price_lookback=range(5, 11),
                        sma_window=range(14, 36, 7))'''

    # And run it
    print('Starting Portfolio Value: %.2f' % cerebro.broker.getvalue())
    back = cerebro.run(maxcpus=1)
    print('Final Portfolio Value: %.2f' % cerebro.broker.getvalue())

    # Parse optimisation results
    par_list = [[x[0].params.vol_window,
                 x[0].params.vol_roc_period,
                 x[0].params.price_lookback,
                 x[0].params.fast_period,
                 x[0].params.slow_period,
                 x[0].params.sig_period,
                 x[0].analyzers.returns.get_analysis()['rnorm100'],
                 x[0].analyzers.drawdown.get_analysis()['max']['drawdown'],
                 x[0].analyzers.sharpe.get_analysis()['sharperatio']
                 ] for x in back]

    par_df = pd.DataFrame(par_list, columns = ['vol_window', 'vol_roc_period', 'price_lookback', 'macd_fast', 'macd_slow', 'macd_sig', 'return', 'dd', 'sharpe'])
    return par_df.to_csv("optNew.csv", float_format="%.2f")

    # Plot if requested
    # cerebro.plot(style='candlestick', numfigs=1)