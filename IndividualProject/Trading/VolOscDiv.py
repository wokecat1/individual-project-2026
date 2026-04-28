import backtrader as bt

class VolOscDivergence(bt.Strategy):

    """Volume Oscillator Divergence strategy with ATR trailing stops and volatility-adjusted sizing"""

    params = dict(          # params taken from maximum average of optimisation data
        vol_window=20,      # volatility calculation period
        vol_roc_period=9,   # momentum calculation period
        price_lookback=7,   # price lookback period
        sma_window=28,      # SMA window
        atr_window=14,      # ATR window for trailing stops
        atr_multiplier=2,   # modifier for trailing stop aggressiveness
        rsi_window=18,      # RSI window
        max_hold_bars=30,   # max time a trade can be held
        min_gap_bars=1,     # min time between trades
        max_risk=0.8,       # max capital to risk
        min_risk=0.2,       # min capital to risk
        stop_smooth=0.2
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

            # Minimum trade gap control
            if ind['last_trade_bar'] is not None and (len(d) - ind['last_trade_bar']) < self.p.min_gap_bars:
                continue

            # Trend and volatility adjusted sizing
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

            # Entry signals
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