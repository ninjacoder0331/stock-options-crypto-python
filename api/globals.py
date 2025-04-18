"""
Global variables for the application.
These variables can be imported and used in any module.
"""

# Trading variables
Profit = 0
Loss = 0
buyPrice = -1

# Function to update profit and loss
async def update_profit_loss(profit, loss):
    global Profit, Loss
    Profit = profit
    Loss = loss
    return Profit, Loss

# Function to update buy price
async def update_buy_price(price):
    global buyPrice
    buyPrice = price
    return buyPrice

# Function to get all global variables
def get_global_variables():
    global Profit, Loss, buyPrice
    return {
        "profit": Profit,
        "loss": Loss,
        "buyPrice": buyPrice
    }