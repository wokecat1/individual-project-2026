import backtrader as bt

class MACD(bt.Strategy):

    """Trading strategy using a Moving Average Convergence/Divergence indicator"""

    params = dict(              # params taken from maximum average of optimisation data
        fast_period=12,         # period for fast MA
        slow_period=40,         # period for slow MA
        sig_period=13,          # period for MACD signal
        atr_period=14,          # ATR period for stops
        atr_multiplier=2.0,     # ATR value scalar
        max_hold_bars=30,       # max time a trade can be held
        min_gap_bars=1,         # min time between trades
        max_risk=0.8,           # max capital to risk
        min_risk=0.2,           # min capital to risk
        trend_smooth_period=3,  # bars to compute slope for trend strength
    )

    # Function to log information to debug console
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