from fastapi import FastAPI, HTTPException , WebSocket, WebSocketDisconnect
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from .routes import auth
from .routes import trader
from .routes import brokerage
from .globals import Profit, Loss
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
import logging

from typing import Dict, Set, List, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
load_dotenv()

app = FastAPI()

entry_price = 0
updated_entry_price = 0
number_of_times = 0
signal_is_open = False
profit_percent = 2
lose_percent = 0.3
symbol = "UVIX"
order_id = ""
check_in_order_status = False

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

async def update_profit_loss_from_db():
    try:
        settings_collection = await get_database("settings")
        settings = await settings_collection.find_one({})
        global Profit, Loss
        Profit = settings["profitPercent"]
        Loss = settings["lossPercent"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
        startStopSettingsCollection = await get_database("startStopSettings")
        startStopSettings = await startStopSettingsCollection.find_one({})
        options_start = startStopSettings["optionsStart"]
        if options_start == False:
            return {"message": "Stock trading is not started"}
        
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
            
            result = await create_options_sell_order()

            return {"message": "Sell order processed", "sell_result->": result}
            
        return {"message": "Signal received", "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

async def create_options_buy_order(sell_symbol, buy_symbol, quantity , strategy , reason):
    try :
        # Configure Alpaca credentials
        alpaca_api = os.getenv("ALPACA_OPTIONS_API_KEY")
        alpaca_secret = os.getenv("ALPACA_OPTIONS_SECRET_KEY")
        formatted_time = await current_time()

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


        response = requests.post(url, json=buy_payload, headers=headers)
        second_result_status = response.status_code
        second_trading_id = response.json()["id"]
        times = 10;
        while second_result_status != 200 and times > 0:
            response = requests.post(url, json=buy_payload, headers=headers)
            second_result_status = response.status_code
            times -= 1

        # print(response.status_code)
        # print("second time" , times)

        response = requests.post(url, json=sell_payload, headers=headers)
        first_result_status = response.status_code
        first_trading_id = response.json()["id"]
        times = 10;
        while first_result_status != 200 and times > 0:
            response = requests.post(url, json=sell_payload, headers=headers)
            first_result_status = response.status_code
            times -= 1
        
        # print(response.status_code)
        # print("first time" , times)

        if first_result_status != 200:
            sell_symbol = ""
        if second_result_status !=200:
            buy_symbol = ""

        if(sell_symbol != "" ):
            url = "https://paper-api.alpaca.markets/v2/orders?status=all&symbols=" + sell_symbol
            response = requests.get(url, headers=headers)
            for order in response.json():
                if order["id"] == first_trading_id:
                    print("***********sell_symbol", sell_symbol)
                    price = order["filled_avg_price"]
                    quantity = order["filled_qty"]
                    sell_quantity = quantity
                    sell_price = price
                    break;

        if(buy_symbol != ""):
            url = "https://paper-api.alpaca.markets/v2/orders?status=all&symbols=" + buy_symbol
            response = requests.get(url, headers=headers)
            for order in response.json():
                if order["id"] == second_trading_id:
                    print("***********buy_symbol", buy_symbol)
                    price = order["filled_avg_price"]
                    quantity = order["filled_qty"]
                    buy_quantity = quantity
                    buy_price = price
                    break;
                    

        options_collection = await get_database("optionsDatabase")
        options_data = {
            "sell_symbol": sell_symbol,
            "sellTradingId": first_trading_id,
            "sellQuantity": sell_quantity,
            "sellSoldQuantity": 0,
            "sellEntryPrice": sell_price,
            "sellExitPrice": None,
            "buy_symbol": buy_symbol,
            "buyTradingId": second_trading_id,
            "buyEntryPrice": buy_price,
            "buyExitPrice": None,
            "buyQuantity": buy_quantity,
            "buySoldQuantity": 0,
            "action": "OPEN",
            "strategy": strategy,
            "reason": reason,
            "tradingType": "auto",
            "entryTimeStamp" : formatted_time,
            "exitTimeStamp" : None,
            "status" : "open"
        }

        await options_collection.insert_one(options_data)

        return {"message": "Buy order processed", "buy_result->": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

async def create_options_sell_order():
    try:
        
        options_collection = await get_database("optionsDatabase")
        options_data = await options_collection.find_one({"status": "open"})
        sell_symbol = options_data["sell_symbol"]
        buy_symbol = options_data["buy_symbol"]
        sell_quantity = options_data["sellQuantity"]
        buy_quantity = options_data["buyQuantity"]
        
        alpaca_api = os.getenv("ALPACA_OPTIONS_API_KEY")
        alpaca_secret = os.getenv("ALPACA_OPTIONS_SECRET_KEY")
        formatted_time = await current_time()
        
        url = "https://paper-api.alpaca.markets/v2/orders"
        
        sell_payload = { 
            "type": "market",
            "time_in_force": "day",
            "symbol": sell_symbol,
            "qty": sell_quantity,
            "side": "buy"
        }

        buy_payload = {
            "type": "market",
            "time_in_force": "day",
            "symbol": buy_symbol,
            "qty": buy_quantity,
            "side": "sell"
        }

        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "APCA-API-KEY-ID": alpaca_api,
            "APCA-API-SECRET-KEY": alpaca_secret
        }

        first_result_status = 0
        first_trading_id = ""
        second_result_status = 0
        second_trading_id = ""
        
        if sell_symbol != "":
            response = requests.post(url, json=sell_payload, headers=headers)
            second_result_status = response.status_code
            times = 10;
            while second_result_status != 200 and times > 0:
                response = requests.post(url, json=sell_payload, headers=headers)
                second_result_status = response.status_code
                if(second_result_status != 200):
                    second_trading_id = response.json()["id"]
                    break;
                times -= 1
            # print("response1", response.status_code)
            print("first time" , times)
        else:
            first_result_status = 200

        if buy_symbol != "":
            response = requests.post(url, json=buy_payload, headers=headers)
            first_result_status = response.status_code
            times = 10;
            while first_result_status != 200 and times > 0:
                response = requests.post(url, json=buy_payload, headers=headers)
                first_result_status = response.status_code
                if(first_result_status != 200):
                    second_trading_id = response.json()["id"]
                    break;
                times -= 1
            # print("response2", first_result_status)
            print("second time" , times)
        else:
            second_result_status = 200

        if first_result_status == 200 and second_result_status == 200:
            if first_trading_id != "":
                url = "https://paper-api.alpaca.markets/v2/orders?status=all&symbols=" + sell_symbol
                response = requests.get(url, headers=headers)
                for order in response.json():
                    if order["id"] == first_trading_id:
                        print("***********sell_symbol", sell_symbol)
                        price = order["filled_avg_price"]
                        quantity = order["filled_qty"]
                        sell_quantity = quantity
                        sell_price = price
                        break;
            
            if second_trading_id != "":
                url = "https://paper-api.alpaca.markets/v2/orders?status=all&symbols=" + buy_symbol
                response = requests.get(url, headers=headers)
                for order in response.json():
                    if order["id"] == second_trading_id:
                        print("***********buy_symbol", buy_symbol)
                        price = order["filled_avg_price"]
                        quantity = order["filled_qty"]
                        buy_quantity = quantity
                        buy_price = price


            options_collection = await get_database("optionsDatabase")
            options_collection.update_one(
                {"status" : "open"},
                {"$set" : {"status" : "closed", "exitTimeStamp" : formatted_time,
                           "sellSoldQuantity" : sell_quantity,
                           "buySoldQuantity" : buy_quantity,
                           "sellExitPrice" : sell_price,
                           "buyExitPrice" : buy_price}}
            )
        logging.info(f"[{datetime.now()}] Sell order created for symbol: {sell_symbol}, quantity: {sell_quantity}")
        # return market_order

        return {"message": "Sell order processed", "sell_result->": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

async def current_time():
    try :
        ntp_client = ntplib.NTPClient()
        response = ntp_client.request('pool.ntp.org')
        currentTime = datetime.fromtimestamp(response.tx_time, ZoneInfo("America/New_York"))
        return currentTime.strftime("%Y-%m-%d %H:%M:%S %Z")
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

class stockSignal(BaseModel):
    order : str
    symbol : str
    price : str

# for stock trading
@app.post("/signal")
async def receive_signal(signal_request: stockSignal):
    print("signal_request", signal_request)
    try:
        startStopSettingsCollection = await get_database("startStopSettings")
        startStopSettings = await startStopSettingsCollection.find_one({})
        stock_start = startStopSettings["stockStart"]
        options_start = startStopSettings["optionsStart"]
        if stock_start == False:
            return {"message": "Stock trading is not started"}
        
        settings = await get_settings()
        stock_amount = settings["stockAmount"]
        
        # Handle buy signals
        if signal_request.order == 'buy':
            check_position = await check_open_position()
            if check_position == False:
                symbol = signal_request.symbol  # Remove quotes from symbol
                price = signal_request.price
                global check_in_order_status
                check_in_order_status = True
                print("symbol", symbol)
                # Your buy order logic here
                result = await create_order(symbol,stock_amount)
                return {"message": "Buy order processed", "buy_result->": result}
            else:
                return {"message": "Buy order already processed", "buy_result->": "already_processed"}
        
        # Handle sell signals
        elif signal_request.order == 'sell':
            return {"message": "Sell order already processed", "sell_result->": "already_processed"}
            # Your sell order logic here
            # print("sellOrder--------->occured")
            symbol = signal_request.symbol  # Remove quotes from symbol
            price = signal_request.price
            result = await create_sell_order(symbol,stock_amount)
            return {"message": "Sell order processed", "sell_result->": result}
            
        return {"message": "Signal received", "data": signal_request}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/test")
async def test_endpoint():
    print("test")
    return {"message":"test url"}

async def create_order(symbol, quantity):
    try:
        global entry_price  # Add this line to access the global variable
        stock_history_collection = await get_database("stockHistory")
        settings_collection = await get_database("settings")
        settings = await settings_collection.find_one({})
        stock_amount = settings["stockAmount"]
        formatted_time = await current_time() 
        alpaca_api = os.getenv("ALPACA_API_KEY")
        alpaca_secret = os.getenv("ALPACA_SECRET_KEY")

        url = "https://paper-api.alpaca.markets/v2/orders"

        payload = {
            "type": "market",
            "time_in_force": "day",
            "symbol": symbol,
            "qty": stock_amount,
            "side": "buy"
        }
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "APCA-API-KEY-ID": alpaca_api,
            "APCA-API-SECRET-KEY": alpaca_secret
        }

        response = requests.post(url, json=payload, headers=headers)
        tradingId = response.json()["id"]


        if tradingId != "":
            await asyncio.sleep(1.5)
            url2 = "https://paper-api.alpaca.markets/v2/orders?status=all&symbols="+symbol
            response2 = requests.get(url2, headers=headers)

            for order in response2.json():
                if order["id"] == tradingId:
                    price = order["filled_avg_price"]
                    buy_quantity = order["filled_qty"]
                    entrytimestamp = order["filled_at"]
                    entry_price = float(price)  # This will now update the global variable
                    global updated_entry_price
                    updated_entry_price = float(price)

                    stop_loss_price = round((updated_entry_price * (1 - lose_percent/100)), 2)
                    take_profit_price = round(updated_entry_price * (1 + profit_percent/100), 2)

                    print("entry_price", entry_price)
                    print("stop_loss_price", stop_loss_price)
                    print("take_profit_price", take_profit_price)

                    await execute_limit_order(symbol, stop_loss_price, take_profit_price)
                    global check_in_order_status
                    check_in_order_status = False
                    
                    history_data = {
                        "symbol": symbol,
                        "quantity": buy_quantity,
                        "entryPrice": price,
                        "exitPrice": 0,
                        "type": "BUY",
                        "tradingId": tradingId,
                        "tradingType" : "auto",
                        "status": "open",
                        "entrytimestamp": entrytimestamp,
                        "exitTimestamp": None
                    }
                    print("buy order is excuted" , entry_price)
                                
                    await stock_history_collection.insert_one(history_data)
                    break;
            

                    
        logging.info(f"[{datetime.now()}] Buy order created for symbol: {symbol}, quantity: {quantity}")
        return entry_price
    except Exception as e:
        return None


async def create_sell_order(symbol):
    try:
        global entry_price
        global updated_entry_price
        global signal_is_open

        entry_price = 0
        updated_entry_price = 0
        signal_is_open = False
        # Save to stockHistory collection
        stock_history_collection = await get_database("stockHistory")
        stock_history = await stock_history_collection.find_one({"symbol": symbol, "status": "open" , "tradingType" : "auto"})
        
        settings_collection = await get_database("settings")
        settings = await settings_collection.find_one({})
        stock_amount = settings["stockAmount"]
        
        if not stock_history:
            return {"message": "No open position found for this symbol", "status": "not_found"}

        tradingId = stock_history["tradingId"]

        # Configure Alpaca credentials
        alpaca_api = os.getenv("ALPACA_API_KEY")
        alpaca_secret = os.getenv("ALPACA_SECRET_KEY")
        url = "https://paper-api.alpaca.markets/v2/orders"

        payload = {
            "type": "market",
            "time_in_force": "day",
            "symbol": stock_history["symbol"],
            "qty": stock_amount,
            "side": "sell"
        }
        # print("payload", payload)
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "APCA-API-KEY-ID": alpaca_api,
            "APCA-API-SECRET-KEY": alpaca_secret
        }

        response = requests.post(url, json=payload, headers=headers)
        tradingId = response.json()["id"]
        # print("response", response.json())
        # print("tradingId", tradingId)
        
        if response.status_code == 200:
            await asyncio.sleep(3)
            url = "https://paper-api.alpaca.markets/v2/orders?status=all&symbols="+symbol
            # url = "https://paper-api.alpaca.markets/v2/orders?status=all&symbols=" + stock_history["symbol"]

            # print("url", url)
            response = requests.get(url, headers=headers)
            price = 0
            for order in response.json():
                if order["id"] == tradingId:
                    price = order["filled_avg_price"]
                    
                    exitTimestamp = order["filled_at"] 
                    # print("----------------------------", price)
                    print("sell order is excuted" , price)
                    await stock_history_collection.update_one(
                        {"symbol": symbol, "status": "open" , "tradingType" : "auto" },
                        {"$set": {"status": "closed" , "exitPrice" : price , "exitTimestamp" : exitTimestamp}}
                    )
                    return {"message": "Sell order processed successfully", "status": "success", "exitPrice": price}
                break;
        
        return {"message": "Failed to process sell order", "status": "error"}
        
    except Exception as e:
        return None


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
        trader_collection = await get_database("traders")
        count = await trader_collection.count_documents({})
        return {"total_traders": count}
        return {"message": "Hello World"}
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
                "profitPercent" : 0,
                "lossPercent" : 0,
            }
            settings_collection.insert_one(settings)
        else:
            settings = {
                "stockAmount" : settings["stockAmount"],
                "optionsAmount" : settings["optionsAmount"],
                "profitPercent" : settings["profitPercent"],
                "lossPercent" : settings["lossPercent"],
            }

        return settings
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/getStartStopSettings")
async def getStartStopSettings():
    try:
        settings_collection = await get_database("startStopSettings")
        settings = await settings_collection.find_one({})
        
        if settings is None:
            # Create default settings
            default_settings = {
                "stockStart": False,
                "optionsStart": False,
            }
            # Insert the default settings into the database
            await settings_collection.insert_one(default_settings)
            return default_settings
        else:
            # Return existing settings
            return {
                "stockStart": settings["stockStart"],
                "optionsStart": settings["optionsStart"],
            }
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

class ProfitLossSettings(BaseModel):
    profitPercent: float
    lossPercent: float

@app.post("/saveProfitLossSettings")
async def saveProfitLossSettings(settings: ProfitLossSettings):
    try:
        settings_collection = await get_database("settings")
        await settings_collection.update_one({}, {"$set": settings.model_dump()}, upsert=True)
        # Update global variables
        await update_profit_loss_from_db()
        return 200
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class StartStopSettings(BaseModel):
    stockStart: bool

@app.post("/changeStockTradingStart")
async def changeStockTradingStart(start: StartStopSettings):
    try:
        settings_collection = await get_database("startStopSettings")
        await settings_collection.update_one({}, {"$set": {"stockStart": start.stockStart}}, upsert=True)
        return 200
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class OptionsStartStopSettings(BaseModel):
    optionsStart: bool

@app.post("/changeOptionsTradingStart")
async def changeOptionsTradingStart(start: OptionsStartStopSettings):
    try:
        settings_collection = await get_database("startStopSettings")
        await settings_collection.update_one({}, {"$set": {"optionsStart": start.optionsStart}}, upsert=True)
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

async def execute_limit_order(symbol, stop_loss_price, take_profit_price):
    try:
        global order_id
        result = await remove_limit_order()
        url = "https://paper-api.alpaca.markets/v2/orders"
        payload = {
            "type": "stop",
            "time_in_force": "day",
            "symbol": symbol,
            "qty": "100",
            "side": "sell",
            "stop_price": stop_loss_price
        }
        ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
        ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "APCA-API-KEY-ID": ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY
        }
        print("===========headers======", headers)
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code != 200:
            print(f"Failed to create order. Status code: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
        response_data = response.json()
        if 'id' not in response_data:
            print(f"Response missing 'id' field: {response_data}")
            return None
            
        order_id = response_data["id"]
        print("order_id", order_id)
        return response_data
    except Exception as e:
        print(f"Error in execute limit order: {e}")
        return None

async def remove_limit_order():
    try:
        global order_id
        url = "https://paper-api.alpaca.markets/v2/orders"
        ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
        ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "APCA-API-KEY-ID": ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY
        }

        response = requests.delete(url, headers=headers)
        return {"status": "success"}
    except Exception as e: 
        print(f"Error in remove limit order: {e}")
        return {"status": "error"}

@app.get("/checkOpenPosition")
async def check_open_position():
    try:
        global symbol
        ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
        ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "APCA-API-KEY-ID": ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY
        }
        url = "https://paper-api.alpaca.markets/v2/positions/" + symbol

        response = requests.get(url, headers=headers)
        # print("response", response.json())
        if response.status_code == 200:
            return True
        else:
            global entry_price
            global updated_entry_price
            global order_id
            entry_price = 0
            updated_entry_price = 0
            order_id = ""
            return False

    except Exception as e:
        print(f"Error in check open position: {e}")
        return None 


async def check_funtion():
    try:
        global signal_is_open
        global profit_percent
        global lose_percent
        global updated_entry_price
        global symbol
        global order_id
        global number_of_times
        global check_in_order_status

        if check_in_order_status == True:
            return

        check = await check_open_position()

        if check == True:
            global entry_price
            number_of_times += 1
            print("================entry_price=========", entry_price)
            
            url = "https://paper-api.alpaca.markets/v2/positions/" + symbol

            ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
            ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

            headers = {
                "accept": "application/json",
                "APCA-API-KEY-ID": ALPACA_API_KEY,
                "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY
            }
            response = requests.get(url, headers=headers)
            bid_price = response.json()["current_price"]
            

            updated_entry_price = float(bid_price)
            if entry_price < updated_entry_price:
                entry_price = updated_entry_price

            
            take_profit = round(updated_entry_price * (1 + profit_percent/100), 2)
            stop_loss = round(entry_price * (1 - lose_percent/100), 2)

            print("current_price", bid_price)
            print("stop_loss" , stop_loss)
            print("take profit" , take_profit)

            await execute_limit_order(symbol, stop_loss, take_profit)

        else:
            order_id = ""
            number_of_times = 0
        return "HOLD"
    except Exception as e:
        print(f"Error in function: {str(e)}")
        return "Error occurred"

scheduler = AsyncIOScheduler()

@app.on_event("startup")
async def start_scheduler():
    scheduler.start()
    # Initialize global variables
    await update_profit_loss_from_db()

# Shutdown the scheduler when the application stops
@app.on_event("shutdown")
async def shutdown_scheduler():
    scheduler.shutdown()

scheduler.add_job(
        check_funtion,
        trigger='interval',
        seconds=60,
        timezone=ZoneInfo("America/New_York"),
        misfire_grace_time=None
    )

@app.get("/getAllStockData")
async def get_all_stock_data():
    try:
        stock_history_collection = await get_database("stockHistory")
        stock_data = await stock_history_collection.find().to_list(1000)
        
        # Convert ObjectId to string for JSON serialization
        for stock in stock_data:
            stock["_id"] = str(stock["_id"])
            
        return stock_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    