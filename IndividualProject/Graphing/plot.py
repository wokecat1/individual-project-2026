from __future__ import division
import numpy as np

from matplotlib.pylab import plot, ylim, xlim, show, xlabel, ylabel, grid, title
from Database import db

def moving_average(interval, window_size):
    window = np.ones(int(window_size))/float(window_size)
    return np.convolve(interval, window, 'same')

def graph(frame, ticker):
    df = db.frames[frame]
    x = df['Date']
    y = df['Close']
    y_avg = moving_average(y, 15)

    # Plot closing price of stock
    headers = df.columns.values.tolist()
    plot(x, y, "k", label='Closing Price') # Close data
    plot(x, y_avg, "r", label='Closing Price SMA', linewidth=2) # Closing price SMA
    xlabel('Date')
    ylabel('Stock Closing Price ($)')
    title(ticker + ' Stock Price During Simulation Scenario')
    grid(True)
    show()