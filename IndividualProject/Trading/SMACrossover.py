from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import numpy as np

class SMACrossover(bt.SignalStrategy):

    """Simpler trading strategy which uses the crossover of a slower and a faster SMA as an indicator"""

    params = dict(          # params taken from maximum average of optimisation data
        pfast=6,            # period for the fast moving average
        pmid=18,            # period for the medium moving average
        pslow=31,           # period for the slow moving average
        max_hold_bars=30,   # max time a trade can be held
        min_gap_bars=1,     # min time between trades
        max_risk=0.8,       # max capital to risk
        min_risk=0.2,       # min capital to risk
    )

    # Function to log information to debug console
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

            # Active order check
            if ind['order']:
                continue

            # Max hold exit
            if pos and ind['entry_bar']:  # entry bar
                if (len(d) - ind['entry_bar']) >= self.p.max_hold_bars:
                    self.close(data=d)
                    ind['entry_bar'] = None
                    ind['last_trade_bar'] = len(d)
                    continue

            # Trailing stops
            if pos:
                # Decide whether to exit trade
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

            # Position sizing
            sma_angle = abs((sma_slow_slope - sma_fast_slope) / (1 + sma_slow_slope * sma_fast_slope))  # angle between slopes
            trend_strength = np.arctan(sma_angle) / (np.pi / 2)                                         # 0 when slopes are parallel, 1 when perpendicular
            size_factor = min(self.p.max_risk, max(self.p.min_risk, trend_strength))                      # trend strength clipped between 0.2 and 0.8
            cash = self.broker.getcash()
            size = int(cash * size_factor / current_price)                                              # number of shares buyable with capital being risked
            if size <= 0:
                continue

            # Entry conditions
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