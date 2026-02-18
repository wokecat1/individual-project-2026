from Application import cli, __app_name__, __version__
from Database import db
from Trading import algs
from Graphing import plot
from cmd import Cmd
import re

class AppPrompt(Cmd):

    def do_start(self, sim):
        """Simulation scenario and trading algorithm selector."""
        print("Select simulation number between 1 and 10.")
        num = int(input('Enter simulation number: '))
        if num in range (1, 16):
            db.import_data(num)
        else:
            print("Scenario not found, please select a number between 1 and 16")
            raise SystemError

        print(
"""Select algorithm to run.
    1 - Simple SMA
    2 - SMA Crossover
    3 - Adaptive MAC
    4 - MACD
    5 - RSI
    6 - Bollinger Bands
    7 - Volume Oscillator Divergence"""
                  )
        num2 = int(input('Enter simulation number: '))
        if num2 in range(1, 10):
            print("Do you want to run the simulation on all stocks? (y/n)")
            com = input('Enter choice: ')
            if com == 'y':
                algs.runall(db.frames, num2)
            elif com == 'n':
                print("Enter stock to run simulation on.")
                com2 = input('Enter choice: ')
                if com2 in db.tickers:
                    algs.runone(com2, num2)
                else:
                    print("Stock not found, please select a valid stock ticker.")
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
                   'List of stocks: ' + re.sub(r'[\'\[\]]', '', str(db.tickers)))