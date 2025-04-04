from fastapi import FastAPI, HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from .routes import auth
from .routes import trader
from .routes import brokerage
import os
import re
import asyncio
from .database import get_database
from pydantic import BaseModel
import requests
import ntplib
from datetime import datetime
from zoneinfo import ZoneInfo
from .routes.utils import parse_option_date
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# import alpaca_trade_api as tradeapi

# from alpaca.trading.client import TradingClient
# from alpaca.trading.enums import OrderSide, TimeInForce
# from alpaca.trading.requests import MarketOrderRequest
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()



app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

class SignalRequest(BaseModel):
    message: str

    def parse_signal(self):
        # Parse the message like "buySignal\nsymbol : CRYPTO10\nprice : 17697.7"
        lines = self.message.split('\n')
        
        signal_type = lines[0]  # "buySignal" or "sellSignal"
        
        # Extract symbol and price using regex or split
        symbol_match = re.search(r'symbol : (.+)', self.message)
        quantity_match = re.search(r'quantity : (.+)', self.message)
        price_match = re.search(r'price : (.+)', self.message)
        
        symbol = symbol_match.group(1) if symbol_match else None
        quantity = float(quantity_match.group(1)) if quantity_match else None
        price = float(price_match.group(1)) if price_match else None
        
        return {
            "signal_type": signal_type,
            "symbol": symbol,
            "quantity": quantity,
            "price": price
        }
    

@app.post("/signal")
async def receive_signal(signal_request: SignalRequest):
    try:
        parsed_data = signal_request.parse_signal()
        logger.info(f"[{datetime.now()}] Received signal endpoint called with data: {parsed_data}")
        settings = await get_settings()
        stock_amount = settings["stockAmount"]
        options_amount = settings["optionsAmount"]
        
        # Handle buy signals
        if parsed_data["signal_type"] == "buy":
            symbol = parsed_data["symbol"]
            quantity = parsed_data["quantity"]
            price = parsed_data["price"]
            # Your buy order logic here
            result = await create_order(symbol,stock_amount,price)
            return {"message": "Buy order processed", "buy_result->": result}
        
        # Handle sell signals
        elif parsed_data["signal_type"] == "sell":
            # Your sell order logic here
            print("sellOrder--------->occured")
            symbol = parsed_data["symbol"]
            quantity = parsed_data["quantity"]
            price = parsed_data["price"]
            result = await create_sell_order(symbol,stock_amount, price)
            return {"message": "Sell order processed", "sell_result->": result}
            
        return {"message": "Signal received", "data": parsed_data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/shortStockSignal")
async def short_stock_signal(signal_request: SignalRequest):
    try:
        parsed_data = signal_request.parse_signal()
        logger.info(f"[{datetime.now()}] Received signal endpoint called with data: {parsed_data}")
        
        # Handle buy signals
        if parsed_data["signal_type"] == "buy":
            symbol = parsed_data["symbol"]
            quantity = parsed_data["quantity"]
            price = parsed_data["price"]
            # Your buy order logic here
            result = await create_short_stock_order(symbol,quantity,price)
            return {"message": "Buy order processed", "buy_result->": result}
        
        # Handle sell signals
        elif parsed_data["signal_type"] == "sell":
            # Your sell order logic here
            print("sellOrder--------->occured")
            symbol = parsed_data["symbol"]
            quantity = parsed_data["quantity"]
            price = parsed_data["price"]
            result = await create_short_stock_sell_order(symbol, quantity, price)
            return {"message": "Sell order processed", "sell_result->": result}
            
        return {"message": "Signal received", "data": parsed_data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class OptionsData(BaseModel):
    sell_close: str
    buy_close: str

class OptionsSignal(BaseModel):
    action: str
    strategy: str
    quantity: int
    options: OptionsData
    reason: str

async def get_settings():
    try:
        settings_collection = await get_database("settings")
        settings = await settings_collection.find_one({})
        return settings
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/optionsTrading")
async def options_trading(signal_request: OptionsSignal):
    try:
        print("signal_request", signal_request)
        sell_symbol = signal_request.options.sell_close
        buy_symbol = signal_request.options.buy_close

        settings = await get_settings()
        stock_amount = settings["stockAmount"]
        options_amount = settings["optionsAmount"]

        # return {"stock_amount": stock_amount, "options_amount": options_amount}
        # quantity = signal_request.quantity
        
        if signal_request.action == "OPEN":
            print("open signal")
            result = await create_options_buy_order(sell_symbol,buy_symbol,options_amount , signal_request.strategy , signal_request.reason)
            return {"message": "Buy order processed", "buy_result->": result}

        # Handle sell signals
        elif signal_request.action == "CLOSE":
            # Your sell order logic here
            print("close signal")

            options_collection = await get_database("optionsDatabase")
            options_data = await options_collection.find_one(
                {"status" : "open"}
            )

            print("options_data", options_data)
            if options_data:
                sell_symbol = options_data["sell_symbol"]
                buy_symbol = options_data["buy_symbol"]
                quantity = options_data["quantity"]
                result = await create_options_sell_order(sell_symbol,buy_symbol,options_amount , signal_request.strategy , signal_request.reason)

            return {"message": "Sell order processed", "sell_result->": result}
            
        return {"message": "Signal received", "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

async def create_options_buy_order(sell_symbol, buy_symbol, quantity , strategy , reason):
    try :
        # Configure Alpaca credentials
        alpaca_api = os.getenv("ALPACA_OPTIONS_API_KEY")
        alpaca_secret = os.getenv("ALPACA_OPTIONS_SECRET_KEY")

        url = "https://paper-api.alpaca.markets/v2/orders"

        sell_payload = {
            "type": "market",
            "time_in_force": "day",
            "symbol": sell_symbol,
            "qty": quantity,
            "side": "sell"
        }   

        buy_payload = {
            "type": "market",
            "time_in_force": "day",
            "symbol": buy_symbol,
            "qty": quantity,
            "side": "buy"
        }

        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "APCA-API-KEY-ID": alpaca_api,
            "APCA-API-SECRET-KEY": alpaca_secret
        }

        print("sell_payload", sell_payload)
        print("buy_payload", buy_payload)

        response = requests.post(url, json=sell_payload, headers=headers)
        first_result_status = response.status_code
        times = 10;
        while first_result_status != 200 and times > 0:
            response = requests.post(url, json=sell_payload, headers=headers)
            first_result_status = response.status_code
            times -= 1
        
        print(response.status_code)
        print("first time" , times)

        response = requests.post(url, json=buy_payload, headers=headers)
        second_result_status = response.status_code
        times = 10;
        while second_result_status != 200 and times > 0:
            response = requests.post(url, json=buy_payload, headers=headers)
            second_result_status = response.status_code
            times -= 1

        print(response.status_code)
        print("second time" , times)

        if first_result_status == 200 and second_result_status == 200:

            options_collection = await get_database("optionsDatabase")
            options_data = {
                "sell_symbol": sell_symbol,
                "buy_symbol": buy_symbol,
                "quantity": quantity,
                "action": "OPEN",
                "strategy": strategy,
                "reason": reason,
                "status" : "open"
            }

            await options_collection.insert_one(options_data)



        return {"message": "Buy order processed", "buy_result->": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

async def create_options_sell_order(sell_symbol, buy_symbol, quantity , strategy , reason):
    try:
        # Configure Alpaca credentials
        alpaca_api = os.getenv("ALPACA_OPTIONS_API_KEY")
        alpaca_secret = os.getenv("ALPACA_OPTIONS_SECRET_KEY")
        
        print("sell_symbol", sell_symbol)
        print("buy_symbol", buy_symbol)
        print("quantity", quantity)
        url = "https://paper-api.alpaca.markets/v2/orders"
        
        sell_payload = { 
            "type": "market",
            "time_in_force": "day",
            "symbol": sell_symbol,
            "qty": quantity,
            "side": "buy"
        }

        buy_payload = {
            "type": "market",
            "time_in_force": "day",
            "symbol": buy_symbol,
            "qty": quantity,
            "side": "sell"
        }

        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "APCA-API-KEY-ID": alpaca_api,
            "APCA-API-SECRET-KEY": alpaca_secret
        }


        print("sell_payload", sell_payload)
        print("buy_payload", buy_payload)
        response = requests.post(url, json=buy_payload, headers=headers)
        first_result_status = response.status_code
        times = 10;
        while first_result_status != 200 and times > 0:
            response = requests.post(url, json=buy_payload, headers=headers)
            first_result_status = response.status_code
            times -= 1
        # print("response2", first_result_status)
        print("second time" , times)

        response = requests.post(url, json=sell_payload, headers=headers)
        second_result_status = response.status_code
        times = 10;
        while second_result_status != 200 and times > 0:
            response = requests.post(url, json=sell_payload, headers=headers)
            second_result_status = response.status_code
            times -= 1
        # print("response1", response.status_code)
        print("first time" , times)

        if first_result_status == 200 and second_result_status == 200:
            options_collection = await get_database("optionsDatabase")
            options_collection.update_one(
                {"status" : "open"},
                {"$set" : {"status" : "closed"}}
            )
        logging.info(f"[{datetime.now()}] Sell order created for symbol: {sell_symbol}, quantity: {quantity}")
        # return market_order

        return {"message": "Sell order processed", "sell_result->": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

async def create_order(symbol, quantity, price):
    try:

        # Save to stockHistory collection
        stock_history_collection = await get_database("stockHistory")
        history_data = {
            "symbol": symbol,
            "quantity": quantity,
            "price": price,
            "type": "BUY",
            "timestamp": datetime.now()
        }
        await stock_history_collection.insert_one(history_data)
        
        # Your existing order logic (currently commented out)
        # Configure Alpaca credentials
        alpaca_api = os.getenv("ALPACA_API_KEY")
        alpaca_secret = os.getenv("ALPACA_SECRET_KEY")

        url = "https://paper-api.alpaca.markets/v2/orders"

        payload = {
            "type": "market",
            "time_in_force": "day",
            "symbol": symbol,
            "qty": quantity,
            "side": "buy"
        }
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "APCA-API-KEY-ID": alpaca_api,
            "APCA-API-SECRET-KEY": alpaca_secret
        }

        response = requests.post(url, json=payload, headers=headers)

        print(response.text)

        logging.info(f"[{datetime.now()}] Buy order created for symbol: {symbol}, quantity: {quantity}")
        return {"message": "Buy order processed", "buy_result->": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

async def create_short_stock_order(symbol, quantity, price):
    try:

        # Save to stockHistory collection
        stock_history_collection = await get_database("stockHistory")
        history_data = {
            "symbol": symbol,
            "quantity": quantity,
            "type": "BUY",
            "timestamp": datetime.now()
        }
        # print("history_data", history_data)
        await stock_history_collection.insert_one(history_data)
        
        # Your existing order logic (currently commented out)
        # Configure Alpaca credentials
        alpaca_api = os.getenv("ALPACA_SHORT_STOCK_API_KEY")
        alpaca_secret = os.getenv("ALPACA_SHORT_STOCK_SECRET_KEY")
        url = "https://paper-api.alpaca.markets/v2/orders"

        payload = {
            "type": "market",
            "time_in_force": "gtc",
            "qty": quantity,
            "symbol": symbol,
            "side": "buy"
        }
        # print("payload", payload)
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "APCA-API-KEY-ID": alpaca_api,
            "APCA-API-SECRET-KEY": alpaca_secret
        }

        response = requests.post(url, json=payload, headers=headers)

        print(response.text)
        logging.info(f"[{datetime.now()}] Buy order created for symbol: {symbol}, quantity: {quantity}")
        return {"message": "Buy order processed", "buy_result->": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/sellOrder")
async def create_sell_order(symbol, quantity, price):
    try:

        # Save to stockHistory collection
        stock_history_collection = await get_database("stockHistory")
        history_data = {
            "symbol": symbol,
            "quantity": quantity,
            "price": price,
            "type": "SELL",
            "timestamp": datetime.now()
        }
        await stock_history_collection.insert_one(history_data)

        # Configure Alpaca credentials
        alpaca_api = os.getenv("ALPACA_API_KEY")
        alpaca_secret = os.getenv("ALPACA_SECRET_KEY")
        url = "https://paper-api.alpaca.markets/v2/orders"

        payload = {
            "type": "market",
            "time_in_force": "day",
            "symbol": symbol,
            "qty": quantity,
            "side": "sell"
        }
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "APCA-API-KEY-ID": alpaca_api,
            "APCA-API-SECRET-KEY": alpaca_secret
        }

        response = requests.post(url, json=payload, headers=headers)

        print(response.text)
        logging.info(f"[{datetime.now()}] Sell order created for symbol: {symbol}, quantity: {quantity}")

        # return market_order

        return {"message": "Sell order processed", "sell_result->": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

async def create_short_stock_sell_order(symbol, quantity, price):
    try:

        # Save to stockHistory collection
        stock_history_collection = await get_database("stockHistory")
        history_data = {
            "symbol": symbol,
            "quantity": quantity,
            "price": price,
            "type": "SELL",
            "timestamp": datetime.now()
        }
        await stock_history_collection.insert_one(history_data)

        # Configure Alpaca credentials
        alpaca_api = os.getenv("ALPACA_SHORT_STOCK_API_KEY")
        alpaca_secret = os.getenv("ALPACA_SHORT_STOCK_SECRET_KEY")
        

        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "APCA-API-KEY-ID": alpaca_api,
            "APCA-API-SECRET-KEY": alpaca_secret
        }

        url = "https://paper-api.alpaca.markets/v2/positions"
        response = requests.get(url, headers=headers)
        positions = response.json()
        qty = 0
        for position in positions:
            if position["symbol"] == symbol:
                qty = position["qty"]
                break
        
        # print("positions", positions)
        # print("quantity", qty)
        url = "https://paper-api.alpaca.markets/v2/orders"
        
        payload = {
            "type": "market",
            "time_in_force": "gtc",
            "qty": qty,
            "symbol": symbol,
            "side": "sell"
        }
        
        response = requests.post(url, json=payload, headers=headers)

        print(response.text)    
        logging.info(f"[{datetime.now()}] Sell order created for symbol: {symbol}, quantity: {quantity}")
        # return market_order

        return {"message": "Sell order processed", "sell_result->": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/account")
async def get_account():
    logger.info(f"[{datetime.now()}] Account endpoint called")

    # Configure Alpaca credentials
    alpaca_api = os.getenv("ALPACA_API_KEY")
    alpaca_secret = os.getenv("ALPACA_SECRET_KEY")
    
    headers = {
        "accept": "application/json",
        "APCA-API-KEY-ID": alpaca_api,
        "APCA-API-SECRET-KEY": alpaca_secret
    }
    url = "https://paper-api.alpaca.markets/v2/account/portfolio/history?intraday_reporting=market_hours&pnl_reset=per_day"

    headers = {
        "accept": "application/json",
        "APCA-API-KEY-ID": alpaca_api,
        "APCA-API-SECRET-KEY": alpaca_secret
    }

    response = requests.get(url, headers=headers)


    # print("myassets")
    myassets = response.json()
    url = "https://paper-api.alpaca.markets/v2/positions"

    response = requests.get(url, headers=headers)

    # print("myposition")
    myposition = response.json()

    # myorders = get_all_orders()
    myorders = await get_all_orders()
    # print("myorders")
    buyOrders = 0
    sellOrders = 0
    buyAmount = 0
    sellAmount = 0

    for order in myorders:
        if(order["side"] == "buy"):
            buyOrders += 1
            buyAmount += float(order["filled_qty"])
        elif(order["side"] == "sell"):
            sellOrders += 1
            sellAmount += float(order["filled_qty"])

    # print("buyOrders", buyOrders)
    # print("sellOrders", sellOrders)
    # print("buyAmount", buyAmount)
    # print("sellAmount", sellAmount)

    url = "https://paper-api.alpaca.markets/v2/account"
    response = requests.get(url, headers=headers)
    print("response" , response.text)

    account_info = response.json()
    # Combine both responses into a single dictionary
    combined_data = {
        "portfolio_history": myassets,
        "positions": myposition,
        "account_info": account_info, 
        "orders" : myorders,
        "buyOrders" : buyOrders,
        "sellOrders" : sellOrders,
        "buyAmount" : buyAmount,
        "sellAmount" : sellAmount
    }

    # print("myposition" , myposition)
    return combined_data

@app.get("/get_all_orders")
async def get_all_orders():
    try:
        print("get_all_orders")
        
        CHUNK_SIZE = 1000
        alpaca_api= os.getenv("ALPACA_API_KEY")
        alpaca_secret = os.getenv("ALPACA_SECRET_KEY")
        url = "https://paper-api.alpaca.markets/v2/orders?status=closed&limit=" + str(CHUNK_SIZE)
        headers = {
        "accept": "application/json",
        "APCA-API-KEY-ID": alpaca_api,
        "APCA-API-SECRET-KEY": alpaca_secret
        }

        response = requests.get(url, headers=headers)
        # print(response.json())
        # response = trading_client.get_orders()
        orders = response.json()
        return orders
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/test")
async def test_endpoint():
    print("test")
    return {"message":"test url"}

# db = client.optionsTrading

# Include routers
app.include_router(auth.router, prefix="/api/auth")
app.include_router(trader.router, prefix="/api/trader")
app.include_router(brokerage.router, prefix="/api/brokerage")

@app.get("/")
async def read_root():
    return {"message": "Welcome to FastAPI with MongoDB"}

# Example endpoint to get items
@app.get("/items")
async def get_items():
    try:
        # Get count of traders collection
        trader_collection = await get_database("traders")
        count = await trader_collection.count_documents({})
        # print(count)
        # Or get all traders
        return {"total_traders": count}
        # return {"message": "Hello World"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Example endpoint to create an item
@app.post("/items")
async def create_item(item: dict):
    try:
        global traders
        result = await traders.insert_one(item)
        return {"id": str(result.inserted_id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class BuySellOrder(BaseModel):
    symbol: str
    quantity: float

@app.post("/buySellOrder")
async def buySellOrder(buySellOrder: BuySellOrder):
    try:
        print("buySellOrder")
        print(buySellOrder)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/getSettings")
async def getSettings():
    try:
        settings_collection = await get_database("settings")
        settings = await settings_collection.find_one({})

        if(settings == None):
            settings = {
                "stockAmount" : 0,
                "optionsAmount" : 0,
            }
        else:
            settings = {
                "stockAmount" : settings["stockAmount"],
                "optionsAmount" : settings["optionsAmount"],
            }

        return settings
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class Settings(BaseModel):  
    stockAmount: float
    optionsAmount: float

@app.post("/saveSettings")
async def saveSettings(settings: Settings):
    try:
        settings_collection = await get_database("settings")
        await settings_collection.update_one({}, {"$set": settings.model_dump()}, upsert=True)
        return 200
    except Exception as e:  
        raise HTTPException(status_code=500, detail=str(e))
    
async def auto_sell_options(option_symbol , left_amount):
    try:
        api_key = os.getenv("ALPACA_OPTIONS_API_KEY")
        api_secret = os.getenv("ALPACA_OPTIONS_SECRET_KEY")
        headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": api_secret,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        url = "https://paper-api.alpaca.markets/v2/orders"

        side = "sell"
        if left_amount < 0:
            side = "buy"
        else:
            side = "sell"

        payload = {
            "type": "market",
            "time_in_force": "day",
            "symbol": option_symbol,
            "qty": abs(left_amount),
            "side": side,
        }
        print("payload", payload)
        response = requests.post(url, headers=headers, json=payload)
        return response.json()
    except Exception as e:
        print(f"Error in auto sell options: {e}")


async def check_market_time():
    try:
        # Get time from NTP server
        ntp_client = ntplib.NTPClient()
        response = ntp_client.request('pool.ntp.org')
        # Convert NTP time to datetime and set timezone to ET
        current_time = datetime.fromtimestamp(response.tx_time, ZoneInfo("America/New_York"))
    except Exception as e:
        print(f"Error getting NTP time: {e}")
        # Fallback to local time if NTP fails
        current_time = datetime.now(ZoneInfo("America/New_York"))

    print("current_time: ", current_time)
    
    # Check if it's a weekday (0 = Monday, 6 = Sunday)
    if current_time.weekday() >= 5:  # Saturday or Sunday
        return False
    
    # Create time objects for market open and close
    market_open = current_time.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = current_time.replace(hour=16, minute=0, second=0, microsecond=0)
    
    # Check if current time is within market hours
    is_market_open = market_open <= current_time <= market_close
    return is_market_open

async def check_date_expired(option_symbol , left_amount):
    try:
        print("options symbol" , option_symbol)
        month, date = parse_option_date(option_symbol)
        try:
            # Get time from NTP server
            ntp_client = ntplib.NTPClient()
            response = ntp_client.request('pool.ntp.org')
            # Convert NTP time to datetime and set timezone to ET
            current_time = datetime.fromtimestamp(response.tx_time, ZoneInfo("America/New_York"))
        except Exception as e:
            print(f"Error getting NTP time: {e}")
            # Fallback to local time if NTP fails
            current_time = datetime.now(ZoneInfo("America/New_York"))
            
        # Create expiration date object (40 minutes before market close)
        expiration_date = current_time.replace(month=int(month), day=int(date), hour=15, minute=20, second=0, microsecond=0)
        
        # Check if current time is on expiration date and 40 minutes before close
        if current_time.date() == expiration_date.date() and current_time >= expiration_date:
            print(f"Option {option_symbol} is 40 minutes before market close on expiration date")
            await auto_sell_options(option_symbol , left_amount)
            return True
        else:
            print(f"Current time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Expiration check time: {expiration_date.strftime('%Y-%m-%d %H:%M:%S')}")
            return False
            
    except Exception as e:
        print(f"Error in date expired check: {e}")
        return False


async def check_funtion():
    try:
        # First check if market is open
        is_market_open = await check_market_time()
        if not is_market_open:
            print("Market is closed. Skipping position checks.")

            # return "Market is closed"
        else : 
            print("Market is open")

        api_key = os.getenv("ALPACA_OPTIONS_API_KEY")
        api_secret = os.getenv("ALPACA_OPTIONS_SECRET_KEY")

        url = "https://paper-api.alpaca.markets/v2/positions"

        headers = {
            "accept": "application/json",
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": api_secret
        }

        response = requests.get(url, headers=headers)
        for position in response.json():  # assuming 'positions' is your JSON array
            symbol = position["symbol"]
            print("qty", position["qty"])
            if position["asset_class"] != "us_option":
                await check_date_expired(symbol , position["qty"])

        return "Function executed successfully"
    except Exception as e:
        print(f"Error in function: {str(e)}")
        return "Error occurred"

scheduler = AsyncIOScheduler()

scheduler.add_job(
    check_funtion,
    trigger='interval',
    seconds=20,     # Run every 5 seconds
    timezone=ZoneInfo("America/New_York"),  # ET timezone
    misfire_grace_time=None  # Optional: handle misfired jobs
)

# Start the scheduler when the application starts
@app.on_event("startup")
async def start_scheduler():
    scheduler.start()

# Shutdown the scheduler when the application stops
@app.on_event("shutdown")
async def shutdown_scheduler():
    scheduler.shutdown()