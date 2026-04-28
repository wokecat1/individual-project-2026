This is my Individual Project, created in partial fulfillment of the requirements for completing the 3rd year of my Master's in Computer Science at the University of Sussex. 

This project is a prototype program intended to be used via a Python IDE of some sort, and takes inputs through the IDE's command-line interface. It has been tested in PyCharm and Visual Studio. The user will select a strategy from a list of seven that have been developed, and run it over historical stock data in order to gather information about performance. The program is capable of producing debug logs showing detailed trade timing and cost breakdowns, as well as a graphical representation of the trade simulation. An option is also available to run a given strategy through an optimisation process, but THIS IS NOT RECOMMENDED as the system I currently use requires modifying multiple parameters within the script itself, and as such it currently will not work correctly outside of very specific use cases. 

To run the program, open __main__.py, type "start" and follow the prompts provided by the program to select desired strategy, stock ticker and scenario.

This project was made with assistance of code developed by PyQuantLab and Daniel Rodriguez, and the structure was inspired by algorithmic trading literature by Treleaven et al., Gumparthi et al. and Ernest P. Chan. 
