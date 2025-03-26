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

@router.get("/openpositions")
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

