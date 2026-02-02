from Application import cli, __app_name__, __version__
from Database import db
from Algorithms import algs
from Graphing import plot
from cmd import Cmd

class AppPrompt(Cmd):

    def do_start(self, sim):
        """Simulation scenario selector. Numbers 1-10 for historical data, 11-16 for non-historical simulated data"""
        num = int(sim)
        if num in range (1, 16):
            db.import_data(num)
            algs.run(db.frames)
        else:
            print("Scenario not found, please select a number between 1 and 16")
            raise SystemError

    def do_alg(self, alg):
        """Trading algorithm selector.
           1:
           2:
           3:
           4: """

    def do_quit(self):
        """Quits program."""
        print("Quitting...")
        raise SystemExit

if __name__ == "__main__":
    print(f"{__app_name__} v{__version__}")
    print("Created by Riley Guise")
    prompt = AppPrompt()
    prompt.prompt = '->'
    prompt.cmdloop('Starting up...')