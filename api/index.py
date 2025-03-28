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
from datetime import datetime
from .database import get_database
from pydantic import BaseModel
import requests

# import alpaca_trade_api as tradeapi

# from alpaca.trading.client import TradingClient
# from alpaca.trading.enums import OrderSide, TimeInForce
# from alpaca.trading.requests import MarketOrderRequest
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# if platform.system()=='Windows':
#     asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
# else:
#     asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
# Load environment variables
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
        
        # Handle buy signals
        if parsed_data["signal_type"] == "buy":
            symbol = parsed_data["symbol"]
            quantity = parsed_data["quantity"]
            price = parsed_data["price"]
            # Your buy order logic here
            result = await create_order(symbol,quantity,price)
            return {"message": "Buy order processed", "buy_result->": result}
        
        # Handle sell signals
        elif parsed_data["signal_type"] == "sell":
            # Your sell order logic here
            print("sellOrder--------->occured")
            symbol = parsed_data["symbol"]
            quantity = parsed_data["quantity"]
            price = parsed_data["price"]
            result = await create_sell_order(symbol,quantity, price)
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

@app.post("/optionsTrading")
async def options_trading(signal_request: OptionsSignal):
    try:
        print("signal_request", signal_request)
        sell_symbol = signal_request.options.sell_close
        buy_symbol = signal_request.options.buy_close
        quantity = signal_request.quantity
        
        # Handle buy signals
        if signal_request.action == "OPEN":
            print("open signal")

            # Your buy order logic here
            result = await create_options_buy_order(sell_symbol,buy_symbol,quantity , signal_request.strategy , signal_request.reason)
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
                result = await create_options_sell_order(sell_symbol,buy_symbol,quantity , signal_request.strategy , signal_request.reason)

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


