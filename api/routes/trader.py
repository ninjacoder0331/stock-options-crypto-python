from fastapi import APIRouter, HTTPException
from ..database import get_database
from bson import ObjectId
from pydantic import BaseModel
from ..models.brokerage import Brokerage
import os
import requests
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

@router.get("/getTraders")
async def get_traders():
    try:
        trader_collection = await get_database("traders")
        traders = await trader_collection.find().to_list(1000)
        
        # Convert ObjectId to string for JSON serialization
        for trader in traders:
            trader["_id"] = str(trader["_id"])
            if "user_id" in trader:
                trader["user_id"] = str(trader["user_id"])
                
        return traders
    except Exception as e:
        print(f"Error fetching traders: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch traders")

# using another api key and secret key for options trading |  stock trading is using another api key and secret key

@router.get("/getAnalysts")
async def get_analysts():
    try:
        analyst_collection = await get_database("analyst")
        analysts = await analyst_collection.find().to_list(1000)
        
        # Convert ObjectId to string for JSON serialization
        for analyst in analysts:
            analyst["_id"] = str(analyst["_id"])
                
        return analysts
    except Exception as e:
        print(f"Error fetching analysts: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch analysts")

class UpdateBrokerage(BaseModel):
    traderId: str
    brokerageName : str
    

@router.post("/updateBrokerage")
async def update_brokerage(brokerage: UpdateBrokerage):
    try:
        trader_collection = await get_database("traders")
        result = await trader_collection.update_one(
            {"_id": ObjectId(brokerage.traderId)},
            {"$set": {"brokerageName": brokerage.brokerageName}}
        )
        return {"message": "Brokerage updated successfully"}
    except Exception as e:
        print(f"Error updating brokerage: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update brokerage")
    
# using another api key and secret key for options trading |  stock trading is using another api key and secret key

@router.get("/closedpositions")
async def get_open_positions():
    try:
        # print("openpositions")
        
        CHUNK_SIZE = 1000
        alpaca_api= os.getenv("ALPACA_OPTIONS_API_KEY")
        alpaca_secret = os.getenv("ALPACA_OPTIONS_SECRET_KEY")
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
        # print("orders", orders)
        return orders
    except Exception as e:
        print(f"Error fetching open positions: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch open positions")

@router.get("/openpositions")
async def get_open_positions():
    try:
        # print("openpositions")
        
        CHUNK_SIZE = 1000
        alpaca_api= os.getenv("ALPACA_OPTIONS_API_KEY")
        alpaca_secret = os.getenv("ALPACA_OPTIONS_SECRET_KEY")
        # url = "https://paper-api.alpaca.markets/v2/orders?status=closed&limit=" + str(CHUNK_SIZE)
        
        url = "https://paper-api.alpaca.markets/v2/positions"
        headers = {
        "accept": "application/json",
        "APCA-API-KEY-ID": alpaca_api,
        "APCA-API-SECRET-KEY": alpaca_secret
        }

        response = requests.get(url, headers=headers)
        options_open_positions = response.json()
        # print(response.json())
        # response = trading_client.get_orders()
        orders = response.json()

        alpaca_api= os.getenv("ALPACA_API_KEY")
        alpaca_secret = os.getenv("ALPACA_SECRET_KEY")
        headers = {
        "accept": "application/json",
        "APCA-API-KEY-ID": alpaca_api,
        "APCA-API-SECRET-KEY": alpaca_secret
        }
        url = "https://paper-api.alpaca.markets/v2/positions"
        response = requests.get(url, headers=headers)
        stock_open_positions = response.json()

        # print("stock orders", response.json())
        # print("orders", orders)
        return_result = {
            "options" : options_open_positions,
            "stocks" : stock_open_positions
        }
        return return_result
    except Exception as e:
        print(f"Error fetching open positions: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch open positions")

class SellOptionsOrder(BaseModel):
    symbol: str
    side : str
    quantity: int

# test this api

@router.post("/sellOptionsOrder")
async def sell_options_order(order: SellOptionsOrder):
    try:
        print("sellOptionsOrder")
        # print(order)
        alpaca_api= os.getenv("ALPACA_OPTIONS_API_KEY")
        alpaca_secret = os.getenv("ALPACA_OPTIONS_SECRET_KEY")
        buy_sell_side = "sell"
        if order.side == "Short":
            buy_sell_side = "buy"
        
        payload = {
            "type": "market",
            "time_in_force": "day",
            "symbol": order.symbol,
            "qty":  order.quantity,
            "side": buy_sell_side,
        }
        
        print("payload" , payload)
        headers = {
                    "accept": "application/json",
                    "content-type": "application/json",
                    "APCA-API-KEY-ID": alpaca_api ,
                    "APCA-API-SECRET-KEY": alpaca_secret
                }
        url = "https://paper-api.alpaca.markets/v2/orders"

        response = requests.post(url, json=payload, headers=headers)
        print(response.status_code)
        print(response.json())

        return response.status_code
    except Exception as e:
        print(f"Error selling options order: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to sell options order")

class CloseStockOrder(BaseModel):
    symbol: str
    side : str
    quantity: int

@router.post("/closeStockOrder")
async def close_stock_order(order: CloseStockOrder):
    try:
        print("sellOptionsOrder")
        # print(order)
        alpaca_api= os.getenv("ALPACA_API_KEY")
        alpaca_secret = os.getenv("ALPACA_SECRET_KEY")

        buy_sell_side = "sell"
        if order.side == "Short":
            buy_sell_side = "buy"
        
        payload = {
            "type": "market",
            "time_in_force": "day",
            "symbol": order.symbol,
            "qty":  order.quantity,
            "side": buy_sell_side,
        }
        
        print("payload" , payload)
        headers = {
                    "accept": "application/json",
                    "content-type": "application/json",
                    "APCA-API-KEY-ID": alpaca_api ,
                    "APCA-API-SECRET-KEY": alpaca_secret
                }
        url = "https://paper-api.alpaca.markets/v2/orders"

        response = requests.post(url, json=payload, headers=headers)
        print(response.status_code)
        # print(response.json())

        return response.status_code
    except Exception as e:
        print(f"Error selling options order: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to sell options order")
