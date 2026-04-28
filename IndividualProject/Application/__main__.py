
"""This module provides a basic Command Line Interface for the user to interact
with the program through the command line of a chosen IDE.
"""

from Application import __author__, __app_name__, __version__, __date__, __vnote__
from Database.db import import_data, __tickers__
from Trading.run_funcs import run_all, run_one, run_opt
from cmd import Cmd
import re

class AppPrompt(Cmd):

    def do_start(self, args):

        """Simulation scenario and trading algorithm selector."""

        # Prompt user to select desired scenario
        print("Select simulation number between 1 and 6.")
        num = int(input('Enter simulation number: '))
        if num in range (1, 7):
            import_data(num)
        else:
            print("Scenario not found, please select a number between 1 and 6")
            raise SystemError

        # If no error, prompt user to select desired strategy
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

        # If valid, prompt user to choose which stocks to run in chosen simulation
        if num2 in range(1, 8):
            print("Do you want to run the strategy on all stocks, one stock or optimise the strategy? (y/n/o)")
            com = input('Enter choice: ')

            if com == 'y':      # run simulation on all available stocks
                run_all(num, import_data(num), num2)

            elif com == 'n':    # run simulation on one chosen stock
                print("Enter stock to run simulation on.")
                com2 = input('Enter choice: ')
                if com2 in __tickers__:
                    run_one(num, com2, import_data(num), num2)
                else:
                    print("Stock not found, please select a valid stock ticker.")

            elif com == 'o': # allow user to select ticker to use for optimisation
                print(f"Enter stock to run optimisation on. WARNING: this will \n "
                      f"not work correctly unless you edit the par_list in the run_funcs.py script.")
                com3 = input('Enter choice: ')
                if com3 in __tickers__:
                    run_opt(num, com3, import_data(num), num2)
                else:
                    print("Stock not found, please select a valid stock ticker.")
            else:
                print("Enter a valid choice.")
                raise SystemError
        else:
            print("Algorithm not recognised, please select a valid option.")
            raise SystemError

    def last_change(self, args):
        """Changes made in most recent version update."""
        print(f"v{__version__}: {__vnote__}")

    def do_quit(self, args):
        """Quits program."""
        print("Quitting...")
        raise SystemExit

if __name__ == "__main__":
    print(f"{__app_name__} v{__version__}", {__date__})
    print(f"Created by {__author__}")
    prompt = AppPrompt()
    prompt.prompt = '->'

    # Print stock ticker list for ease of use at top of CLI loop
    prompt.cmdloop('Ready!\n'
                   'List of stocks: ' + re.sub(r'[\'\[\]]', '', str(__tickers__)) + '\n'
                    'Type "help" for more information.')