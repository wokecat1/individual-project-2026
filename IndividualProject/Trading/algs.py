from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

from cmath import atan
import numpy as np
import backtrader as bt
from Database import db

start_cash = 10000

class SMACrossover(bt.SignalStrategy):

    """Simpler trading strategy which uses the crossover of a slower and a faster SMA as an indicator"""

    params = dict(
        pfast=5,    # period for the fast moving average
        pmid=15,    # period for the medium moving average
        pslow=30,   # period for the slow moving average
        max_hold_bars=30,
        min_gap_bars=1,
        max_risk=0.8,
        min_risk=0.2
    )

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
                'last_trade_bar': None
            }

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

                    self.buy(data=d, size=size)  # enter long
                    ind['entry_bar'] = len(d)
                    ind['last_trade_bar'] = len(d)

                elif (ind['crossover_fm'] < 0 and sma_slow_slope < 0 or
                      ind['crossover_ms'] < 0 and sma_fast_slope < 0): # if MAs cross to downside and slow SMA is negative

                    self.sell(data=d, size=size)  # enter short
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

    params = dict(
        fast_base=7,
        slow_base=20,
        min_period_fast=4,
        max_period_fast=14,
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
            crossover = bt.ind.CrossOver(fast_ma, slow_ma) # indicator to detect when fast_ma and slow_ma cross
            atr = bt.ind.ATR(d, period=14)

            self.inds[d] = dict(
                fast_ma=fast_ma,
                slow_ma=slow_ma,
                crossover=crossover,
                atr=atr,
                entry_bar=None,
                last_trade_bar=None,
                stop_price=None
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
                    self.buy(data=d, size=size)
                    ind['entry_bar'] = len(d)
                    ind['last_trade_bar'] = len(d)
                    ind['stop_price'] = current_price - self.p.atr_multiplier * atr

                elif crossover < 0:
                    self.sell(data=d, size=size)
                    ind['entry_bar'] = len(d)
                    ind['last_trade_bar'] = len(d)
                    ind['stop_price'] = current_price + self.p.atr_multiplier * atr

class MACD(bt.Strategy):

    """Trading strategy using a Moving Average Convergence/Divergence indicator"""

    params = dict(
        fast_period=12,         # period for fast MA
        slow_period=26,         # period for slow MA
        sig_period=9,           # period for MACD signal
        atr_period=14,          # ATR period for stops
        atr_multiplier=2.0,     # ATR value scalar
        max_hold_bars=30,
        min_gap_bars=1,
        max_risk=0.8,
        min_risk=0.2,
        trend_smooth_period=3,  # bars to compute slope for trend strength
    )

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
                stop_price=None
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
                    self.buy(data=d, size=size)
                    ind['entry_bar'] = len(d)
                    ind['stop_price'] = current_price - self.p.atr_multiplier * atr_val
                    ind['last_trade_bar'] = len(d)

                elif crossover < 0:  # MACD bearish crossover
                    self.sell(data=d, size=size)
                    ind['entry_bar'] = len(d)
                    ind['stop_price'] = current_price + self.p.atr_multiplier * atr_val
                    ind['last_trade_bar'] = len(d)

class RSI(bt.Strategy):
    """RSI strategy with smoothed ATR trailing stops and trend-strength sizing"""

    params = dict(
        period=14,          # RSI period
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
                stop_price=None
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
            rsi_slope = (ind['rsi'][0] - ind['rsi'][-self.p.trend_smooth_period]) / self.p.trend_smooth_period
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
                    self.buy(data=d, size=size)
                    ind['entry_bar'] = len(d)
                    ind['stop_price'] = current_price - self.p.atr_multiplier * atr_val
                    ind['last_trade_bar'] = len(d)

                elif current_rsi > self.p.overbought and rsi_slope < 0:  # RSI falling from overbought
                    self.sell(data=d, size=size)
                    ind['entry_bar'] = len(d)
                    ind['stop_price'] = current_price + self.p.atr_multiplier * atr_val
                    ind['last_trade_bar'] = len(d)

class BollingerBands(bt.Strategy):
    """Bollinger Bands strategy with ATR trailing stops, volatility-adjusted sizing, and trend strength scaling"""

    params = dict(
        period=20,
        devfactor=2,
        atr_window=14,
        atr_multiplier=2,
        stop_smooth=0.2,
        max_hold_bars=30,
        min_gap_bars=1,
        max_risk=0.8,
        min_risk=0.2
    )

    def __init__(self):
        self.inds = {}
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
                stop_price=None
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
                if pos.size > 0 and current_price < middle: # long position, price below middle band
                    self.close(data=d)
                    ind['entry_bar'] = None
                    ind['stop_price'] = None
                    ind['last_trade_bar'] = len(d)
                    continue
                elif pos.size < 0 and current_price > middle: # short position, price above middle band
                    self.close(data=d)
                    ind['entry_bar'] = None
                    ind['stop_price'] = None
                    ind['last_trade_bar'] = len(d)
                    continue

                # ATR trailing stop
                if pos.size > 0:
                    new_stop = current_price - self.p.atr_multiplier * atr_val
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
                    new_stop = current_price + self.p.atr_multiplier * atr_val
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
                trend_strength = abs(current_price - middle) / (upper - lower)
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
                if current_price > upper:
                    self.buy(data=d, size=size)
                    ind['entry_bar'] = len(d)
                    ind['stop_price'] = current_price - self.p.atr_multiplier * atr_val
                    ind['last_trade_bar'] = len(d)

                elif current_price < lower:
                    self.sell(data=d, size=size)
                    ind['entry_bar'] = len(d)
                    ind['stop_price'] = current_price + self.p.atr_multiplier * atr_val
                    ind['last_trade_bar'] = len(d)

class VolOscDivergence(bt.Strategy):

    """Volume Oscillator Divergence strategy with ATR trailing stops and volatility-adjusted sizing"""

    params = dict(
        vol_window=30,
        vol_roc_period=7,
        price_lookback=7,
        sma_window=30,
        atr_window=14,
        atr_multiplier=2,
        rsi_window=14,
        max_hold_bars=30,
        min_gap_bars=1,
        max_risk=0.8,
        min_risk=0.2,
        stop_smooth=0.2
    )

    def __init__(self):
        self.inds = {}
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
                stop_price=None
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
                        # smoothing to reduce whipsaws
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
                    self.buy(data=d, size=size)
                    ind['entry_bar'] = len(d)
                    ind['last_trade_bar'] = len(d)
                    ind['stop_price'] = current_price - self.p.atr_multiplier * atr

                # Bearish divergence
                elif price_change > 0 > vol_osc_change and current_price < sma and rsi > 30:
                    self.sell(data=d, size=size)
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

        # Add cash
        cerebro.broker.setcash(start_cash)

        # And run it
        print('Starting Portfolio Value: %.2f' % cerebro.broker.getvalue())
        cerebro.run()
        print('Final Portfolio Value: %.2f' % cerebro.broker.getvalue())
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
    cerebro.addstrategy(strategies[strategy])

    # Add cash
    cerebro.broker.setcash(start_cash)

    # And run it
    print('Starting Portfolio Value: %.2f' % cerebro.broker.getvalue())
    cerebro.run()
    print('Final Portfolio Value: %.2f' % cerebro.broker.getvalue())

    # Plot if requested
    cerebro.plot(style='candlestick', numfigs=1)