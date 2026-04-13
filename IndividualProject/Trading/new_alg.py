from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import numpy as np
import backtrader as bt
import backtrader.analyzers as btanalyzers
import pandas as pd

class ProprietaryAlg(bt.Strategy):

    """Volume Oscillator Divergence-based strategy with secondary MACD indicators, ATR trailing stops and volatility-adjusted sizing"""

    params = dict( # params taken from maximum average of optimisation data
        vol_window=30,      # volatility lookback period
        vol_roc_period=7,   # volatility rate of change period
        price_lookback=7,   # price lookback period
        sma_window=30,      # SMA window
        fast_period=12,     # period for fast MA
        slow_period=26,     # period for slow MA
        sig_period=9,       # period for MACD signal
        atr_window=14,
        atr_multiplier=2,
        rsi_window=18,
        min_gap_bars=1,
        max_risk=0.5,
        min_risk=0.2,
        stop_smooth=0.2,
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

            # VolOscDiv indicators
            returns = bt.ind.PctChange(d.close, period=1)
            vol = bt.ind.StdDev(returns, period=self.p.vol_window)
            vol_osc = bt.ind.ROC(vol, period=self.p.vol_roc_period)
            sma = bt.ind.SMA(d.close, period=self.p.sma_window)

            # MACD indicator (supplementary)
            macd = bt.ind.MACDHisto(
                d.close,
                period_me1=self.p.fast_period,
                period_me2=self.p.slow_period,
                period_signal=self.p.sig_period
            )

            # Trailing stop and RSI
            atr = bt.ind.ATR(d, period=self.p.atr_window)
            rsi = bt.ind.RSI(d.close, period=self.p.rsi_window)

            self.inds[d] = dict(
                returns=returns,
                vol=vol,
                vol_osc=vol_osc,
                sma=sma,
                macd=macd,
                atr=atr,
                rsi=rsi,
                entry_bar=None,
                last_trade_bar=None,
                stop_price=None,
                order=None,
                extreme_price=None
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

    def _calc_size(self, price, atr):
        value = self.broker.getvalue()

        pct_atr = atr / price if price else 0
        if pct_atr > 0:
            risk = min(self.p.max_risk, max(self.p.min_risk, 0.1 / pct_atr))
        else:
            risk = 0.3

        return int((value * risk) / price)

    def next(self):
        for d in self.datas:

            ind = self.inds[d]
            pos = self.getposition(d)

            if ind['order']:
                continue

            # Unpack basic values
            price = d.close[0]
            atr = ind['atr'][0]
            sma = ind['sma'][0]
            rsi = ind['rsi'][0]

            macd = ind['macd'].macd[0]
            signal = ind['macd'].signal[0]
            hist = ind['macd'].histo[0]

            pct_atr = atr / price if price != 0 else 0
            price_slope = (price - d.close[-self.p.price_lookback]) / d.close[-self.p.price_lookback]

            # --- Trend mode classification ---
            trending = abs(price_slope) > 0.05 and pct_atr > 0.015  # detect more consistent trends
            reversal = abs(price_slope) < 0.02 and pct_atr < 0.02   # detect reversals

            if ind['entry_bar'] == len(d):
                continue

            # --- Position management ---
            if pos:
                if trending:
                    mult = 2.0
                else:
                    mult = 1.5

                # ---- Position management ----
                # Long position trailing stop
                if pos.size > 0:
                    # Track highest price since entry
                    if ind['extreme_price'] is None:
                        ind['extreme_price'] = d.high[0]
                    else:
                        ind['extreme_price'] = max(ind['extreme_price'], d.high[0]) # set to today's high if new high

                    stop = ind['extreme_price'] - mult * atr # use extreme value weighted by ATR as stop

                    if ind['stop_price'] is None:
                        ind['stop_price'] = stop
                    else:
                        ind['stop_price'] = max(ind['stop_price'], stop)

                    # Trigger stop on low
                    if d.low[0] <= ind['stop_price']:
                        self.close(data=d)
                        ind['stop_price'] = None
                        ind['extreme_price'] = None
                        continue

                # Short position
                else:
                    if ind['extreme_price'] is None:
                        ind['extreme_price'] = d.low[0]
                    else:
                        ind['extreme_price'] = min(ind['extreme_price'], d.low[0])

                    stop = ind['extreme_price'] + mult * atr

                    if ind['stop_price'] is None:
                        ind['stop_price'] = stop
                    else:
                        ind['stop_price'] = min(ind['stop_price'], stop)

                    if d.high[0] >= ind['stop_price']:
                        self.close(data=d)
                        ind['stop_price'] = None
                        ind['extreme_price'] = None
                        continue

                if reversal:
                    if ind['entry_bar'] and len(d) - ind['entry_bar'] > 30:
                        self.close(data=d)
                        continue

            # --- Entry logic ---
            if not pos:
                # Trending "mode"
                if trending:
                    # Long trend
                    if price > sma and macd > signal and hist > 0:
                        pullback = rsi < 55 or price <= sma

                        if pullback:
                            size = self._calc_size(price, atr)
                            ind['order'] = self.buy(data=d, size=size)
                            ind['regime'] = 'trend'
                            ind['entry_bar'] = len(d)
                            ind['stop_price'] = None
                            ind['extreme_price'] = price
                            continue

                    # Short trend
                    if price < sma and macd < signal and hist < 0:
                        pullback = rsi > 45 or price >= sma

                        if pullback:
                            ind['order'] = size = self._calc_size(price, atr)
                            self.sell(data=d, size=size)
                            ind['regime'] = 'trend'
                            ind['entry_bar'] = len(d)
                            ind['stop_price'] = None
                            ind['extreme_price'] = price
                            continue

                # Mean reversion "mode"
                elif reversal:

                    vol_osc = ind['vol_osc'][0]
                    vol_osc_prev = ind['vol_osc'][-self.p.price_lookback]

                    vol_osc_slope = (vol_osc - vol_osc_prev) / (abs(vol_osc_prev) + 1e-6)

                    # Long reversal
                    if price_slope < 0 < vol_osc_slope and rsi < 65:
                        size = self._calc_size(price, atr)
                        ind['order'] = self.buy(data=d, size=size)
                        ind['regime'] = 'chop'
                        ind['entry_bar'] = len(d)
                        ind['stop_price'] = None
                        ind['extreme_price'] = price
                        continue

                    # Short reversal
                    if price_slope > 0 > vol_osc_slope and rsi > 35:
                        size = self._calc_size(price, atr)
                        ind['order'] = self.sell(data=d, size=size)
                        ind['regime'] = 'chop'
                        ind['entry_bar'] = len(d)
                        ind['stop_price'] = None
                        ind['extreme_price'] = price
                        continue