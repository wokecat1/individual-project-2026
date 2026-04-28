
"""This module comprises a Moving Average Crossover-based trading strategy, with custom
functionality to adaptively reside the moving average window depending on market conditions.
"""

import backtrader as bt
import numpy as np

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
        # Volatility = std dev of percentage price change
        self.vol = bt.ind.StdDev(bt.ind.PctChange(self.data), period=self.p.vol_period)
        self.vol_hist = [] # Volatility history of stock

    def next(self):
        # If not all indicators initialised, do nothing
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

    params = dict(              # params taken from maximum average of optimisation data
        fast_base=5,            # base fast MA value
        slow_base=21,           # base slow MA value
        min_period_fast=5,
        max_period_fast=25,     # bounds for fast MA
        min_period_slow=15,
        max_period_slow=40,     # bounds for slow MA
        vol_period=7,           # volatility lookback period
        vol_factor=1.5,         # volatility weighting modifier in calculations
        atr_window=14,          # ATR window for trailing stops
        atr_multiplier=2,       # modifier for trailing stop aggressiveness
        max_hold_bars=30,       # max time a trade can be held
        min_gap_bars=1,         # min time between trades
        max_risk=0.8,           # max capital to risk
        min_risk=0.2,           # min capital to risk
        trend_smooth_period=3   # bars to compute slope for trend strength
    )

    # Function to log information to debug console
    def log(self, txt, dt=None, data=None):
        data = data or self.datas[0]
        dt = dt or data.datetime.date(0)
        print(f'{dt.isoformat()}, {txt}')

    def __init__(self):
        self.inds = {}
        for d in self.datas:
            # Fast adaptive moving average
            fast_ma = AdaptiveSMA(
                d,
                base_period=self.p.fast_base,
                vol_period=self.p.vol_period,
                vol_factor=self.p.vol_factor,
                min_period=self.p.min_period_fast,
                max_period=self.p.max_period_fast
            )
            # Slow adaptive moving average
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

    # Function to log order status and important values
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

    # Function to log trade gross after trade is completed (closed)
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

            # Active order check
            if ind['order']:
                continue

            # Max hold exit
            if pos and ind['entry_bar'] is not None:
                if len(d) - ind['entry_bar'] >= self.p.max_hold_bars:
                    self.close(data=d)
                    ind['entry_bar'] = None
                    ind['stop_price'] = None
                    ind['last_trade_bar'] = len(d)
                    continue

            # Position management
            if pos:
                # Update trailing stops and check stock performance to decide whether to exit
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

            # Trade minimum gap control
            if ind['last_trade_bar'] is not None and \
                    len(d) - ind['last_trade_bar'] < self.p.min_gap_bars:
                continue

            # Trade sizing based on angle between MA slopes
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

            # Entry conditions
            if not pos:
                # Buy if fast crosses from below to above slow (uptrend)
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

                # Sell if fast crosses from above to below slow (downtrend)
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