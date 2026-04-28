
"""This module comprises a trading strategy based around the Bollinger Bands indicator."""

import backtrader as bt

class BollingerBands(bt.Strategy):

    """Bollinger Bands strategy with ATR trailing stops, volatility-adjusted sizing, and trend strength scaling"""

    params = dict(          # params taken from maximum average of optimisation data
        period=7,           # bollinger band period
        devfactor=2,        # modifier for width of bands
        atr_window=14,      # ATR window for trailing stops
        atr_multiplier=2,   # modifier for trailing stop aggressiveness
        stop_smooth=0.2,    # modifier for position sizing calculations
        max_hold_bars=30,   # max time a trade can be held
        min_gap_bars=1,     # min time between trades
        max_risk=0.8,       # max capital to risk
        min_risk=0.2        # min capital to risk
    )

    # Function to log information to debug console
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

            # Active order check
            if ind['order']:
                continue

            # Trade only in high volatility
            if bandwidth < 0.02:
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

            # Trade minimum gap control
            if ind['last_trade_bar'] is not None and (len(d) - ind['last_trade_bar']) < self.p.min_gap_bars:
                continue

            # Position sizing
            if upper != lower: # weighting based on gap between bands and current price
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

            # Entry conditions
            if not pos:
                if d.close[-1] <= upper < current_price: # current price too low
                    order = self.buy(data=d, size=size)
                    if order:
                        ind['order'] = order
                        self.log(
                            txt=f'BUY CREATE, {current_price:.2f}, bar={len(d)}',
                            data=d
                        )
                    ind['entry_bar'] = len(d)
                    ind['stop_price'] = current_price - self.p.atr_multiplier * atr_val
                    ind['last_trade_bar'] = len(d)

                elif d.close[-1] >= lower > current_price: # current price too high
                    order = self.sell(data=d, size=size)
                    if order:
                        ind['order'] = order
                        self.log(
                            txt=f'SELL CREATE, {current_price:.2f}, bar={len(d)}',
                            data=d
                        )
                    ind['entry_bar'] = len(d)
                    ind['stop_price'] = current_price + self.p.atr_multiplier * atr_val
                    ind['last_trade_bar'] = len(d)