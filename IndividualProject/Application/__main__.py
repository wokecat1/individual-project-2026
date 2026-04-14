from Application import cli, __app_name__, __version__
from Database.db import import_data, tickers
from Trading.run_funcs import run_all, run_one, run_opt
from cmd import Cmd
import re

class AppPrompt(Cmd):

    def do_start(self, args):
        """Simulation scenario and trading algorithm selector."""
        print("Select simulation number between 1 and 6.")
        num = int(input('Enter simulation number: '))
        if num in range (1, 7):
            import_data(num)
        else:
            print("Scenario not found, please select a number between 1 and 6")
            raise SystemError

        print(
"""Select algorithm to run.
    1 - SMA Crossover
    2 - Adaptive MAC
    3 - MACD
    4 - RSI
    5 - Bollinger Bands
    6 - Volume Oscillator Divergence
    7 - Proprietary Algorithm"""
                  )
        num2 = int(input('Enter algorithm number: '))
        if num2 in range(1, 8):
            print("Do you want to run the strategy on all stocks, one stock or optimise the strategy? (y/n/o)")
            com = input('Enter choice: ')
            if com == 'y':
                run_all(num, import_data(num), num2)
            elif com == 'n':
                print("Enter stock to run simulation on.")
                com2 = input('Enter choice: ')
                if com2 in tickers:
                    run_one(num, com2, import_data(num), num2)
                else:
                    print("Stock not found, please select a valid stock ticker.")
            elif com == 'o':
                print("Enter stock to run optimisation on. WARNING: this will not work correctly unless you edit the par_list in the run_funcs.py script.")
                com3 = input('Enter choice: ')
                if com3 in tickers:
                    run_opt(num, com3, import_data(num), num2)
                else:
                    print("Stock not found, please select a valid stock ticker.")

            else:
                print("Enter a valid choice.")
                raise SystemError
        else:
            print("Algorithm not recognised, please select a valid option.")
            raise SystemError

    def do_quit(self, args):
        """Quits program."""
        print("Quitting...")
        raise SystemExit

if __name__ == "__main__":
    print(f"{__app_name__} v{__version__}")
    print("Created by Riley Guise")
    prompt = AppPrompt()
    prompt.prompt = '->'
    prompt.cmdloop('Ready!\n'
                   'List of stocks: ' + re.sub(r'[\'\[\]]', '', str(tickers)))