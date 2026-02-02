from Application import cli, __app_name__, __version__, data
from cmd import Cmd

class prompt(Cmd):

    def do_get_scenario(self, arg):
        """Simulation scenario selector. Numbers 1-10 for historical data, 11-16 for non-historical simulated data"""
        if len(arg) == 1 and arg in range (1, 16):


        else:
            print("Scenario not found, please select a number between 1 and 16")
            raise SystemError

    def do_quit(self):
        """Quits program."""
        print("Quitting...")
        raise SystemExit




if __name__ == "__main__":
    print(f"{__app_name__} v{__version__}")
    print("Created by Riley Guise")