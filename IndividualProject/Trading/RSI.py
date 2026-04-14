import backtrader as bt

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