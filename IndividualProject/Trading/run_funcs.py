from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import backtrader.analyzers as btanalyzers
import pandas as pd

from Database import db
from Trading.SMACrossover import SMACrossover
from Trading.AdaptiveMAC import AdaptiveMAC
from Trading.MACD import MACD
from Trading.RSI import RSI
from Trading.BollingerBands import BollingerBands
from Trading.VolOscDiv import VolOscDivergence
from Trading.ProprietaryAlg import ProprietaryAlg

start_cash = 10000

strategies = {
    1: SMACrossover,
    2: AdaptiveMAC,
    3: MACD,
    4: RSI,
    5: BollingerBands,
    6: VolOscDivergence,
    7: ProprietaryAlg,
}

def run_all(sim, frames, strategy):

    """Function to run a strategy over all available data in a simulation chosen by user."""

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

def run_one(sim, ticker, frames, strategy):

    """Function to run a strategy on one specific ticker in a simulation chosen by user."""

    # Create a cerebro
    cerebro = bt.Cerebro()

    # Add data frames to cerebro as data feeds
    frame = frames[db.tickers.index(ticker)]
    data_feed = bt.feeds.PandasData(dataname=frame)
    cerebro.adddata(data_feed, name=ticker)

    # Add the strategy
    cerebro.addstrategy(strategies[strategy])

    # Add cash and commission (0.1%)
    cerebro.broker.setcash(start_cash)
    cerebro.broker.setcommission(commission=0.001)

    # Add analyzers
    cerebro.addanalyzer(btanalyzers.SharpeRatio, _name="sharpe")
    cerebro.addanalyzer(btanalyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(btanalyzers.Returns, _name="returns")

    # And run it
    print('Starting Portfolio Value: %.2f' % cerebro.broker.getvalue())
    cerebro.run(maxcpus=1)
    print('Final Portfolio Value: %.2f' % cerebro.broker.getvalue())

    # Plot if requested
    cerebro.plot(style='candlestick', numfigs=1)

def run_opt(sim, ticker, frames, strategy):

    """Function to optimise a strategy's parameters. WARNING: this will not
    work correctly unless you edit the par_list in the run_funcs.py script."""

    # Create a cerebro
    cerebro = bt.Cerebro()

    # Add data frames to cerebro as data feeds
    frame = frames[db.tickers.index(ticker)]
    data_feed = bt.feeds.PandasData(dataname=frame)
    cerebro.adddata(data_feed, name=ticker)

    # Add cash and commission (0.1%)
    cerebro.broker.setcash(start_cash)
    cerebro.broker.setcommission(commission=0.001)

    # Add analyzers
    cerebro.addanalyzer(btanalyzers.SharpeRatio, _name="sharpe")
    cerebro.addanalyzer(btanalyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(btanalyzers.Returns, _name="returns")

    match strategy:
        case 1:
            cerebro.optstrategy(SMACrossover,
                        pfast=range(3, 8),
                        pmid=range(10, 21),
                        pslow=range(21, 41))
        case 2:
            cerebro.optstrategy(AdaptiveMAC,
                        fast_base=range(5, 16, 5),
                        slow_base=range(14, 29, 7),
                        min_period_fast=range(2, 6),
                        max_period_fast=range(10, 21, 5),
                        min_period_slow=range(10, 26, 5),
                        max_period_slow=range(25, 46, 5))
        case 3:
            cerebro.optstrategy(MACD,
                        fast_period=range(7, 15),
                        slow_period=range(21, 41),
                        sig_period=range(7, 15))
        case 4:
            cerebro.optstrategy(RSI,
                        period=range(7, 29),
                        overbought=range(55, 71, 5),
                        oversold=range(30, 41, 5))
        case 5:
            cerebro.optstrategy(BollingerBands, period=range(7, 29))
        case 6:
            cerebro.optstrategy(VolOscDivergence,
                        vol_window=range(15, 36, 5),
                        vol_roc_period=range(3, 11),
                        price_lookback=range(5, 11),
                        sma_window=range(14, 36, 7))
        case 7:
            cerebro.optstrategy(ProprietaryAlg,
                        vol_window=range(20, 36, 5),
                        vol_roc_period=range(7, 12, 2),
                        price_lookback=range(7, 12, 2),
                        fast_period=range(7, 15, 3),
                        slow_period=range(21, 41, 5),
                        sig_period=range(7, 15, 2))

    # And run it
    print('Started optimisation...')
    back = cerebro.run(maxcpus=1)
    print('Finished optimisation, upon quitting a .csv file will be added to the "Application" directory.')

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