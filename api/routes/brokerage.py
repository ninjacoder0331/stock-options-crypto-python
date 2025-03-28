from fastapi import APIRouter, HTTPException, Request, Header, Depends
from ..models.trader import TraderCreate, Trader
from bson import ObjectId
from passlib.context import CryptContext # type: ignore
from pydantic import BaseModel
from typing import Optional
from  ..database import get_database
from ..models.brokerage import BrokerageCreate, Brokerage
import os
import requests
from dotenv import load_dotenv
import logging

load_dotenv()

router = APIRouter()
logger = logging.getLogger(__name__)

# Add this near the top with other initializations

@router.get("/getBrokerages")
async def get_brokerages():
    try:
        brokerage_collection = await get_database("brokerageCollection")
        brokerages = await brokerage_collection.find().to_list(1000)
        
        # Convert ObjectId to string for JSON serialization
        for brokerage in brokerages:
            brokerage["_id"] = str(brokerage["_id"])
                
        return brokerages
    except Exception as e:
        print(f"Error fetching brokerages: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch brokerages")

@router.post("/create", response_model=dict)
async def create_brokerage(brokerage: BrokerageCreate):
    try:
        print("brokerage",brokerage)
        brokerage_collection = await get_database("brokerageCollection")    
        print("checked")    
        
        # Create new brokerage
        brokerage_dict = brokerage.model_dump()
        result = await brokerage_collection.insert_one(brokerage_dict)
        return {"id": str(result.inserted_id)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Create a model for the delete request
class DeleteBrokerageRequest(BaseModel):
    brokerageId: str

@router.post("/deleteBrokerage")
async def delete_brokerage(request: DeleteBrokerageRequest):
    try:
        brokerage_collection = await get_database("brokerageCollection")
        
        # Convert string ID to ObjectId
        result = await brokerage_collection.delete_one({"_id": ObjectId(request.brokerageId)})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Brokerage not found")
            
        return {"message": "Brokerage deleted successfully"}
    except Exception as e:
        print(f"Error deleting brokerage: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to delete brokerage")

class GetOptionsChainRequest(BaseModel):
    symbol: str
    optionType: str
    date: str

def merge_options_data(options_data, contract_data):
    """
    Merge options snapshots with contract data.
    """
    merged_array = []

    # Check if both data structures exist
    if options_data and contract_data:
        if 'snapshots' in options_data and 'option_contracts' in contract_data:
            for key, snapshot in options_data['snapshots'].items():
                # Find matching contract
                matching_contract = None
                for contract in contract_data['option_contracts']:
                    if contract['symbol'] == key:
                        matching_contract = contract
                        break

                if matching_contract:
                    # Create merged data
                    latest_quote = snapshot.get('latestQuote', {})
                    greeks = snapshot.get('greeks', {})
                    greek = snapshot.get('greek', {})
                    
                    merged_data = {
                        'symbol': key,
                        'bidPrice': latest_quote.get('bp'),
                        'askPrice': latest_quote.get('ap'),
                        'lastPrice': greek.get('last_price'),
                        'volume': latest_quote.get('volume'),
                        'delta': greeks.get('delta'),
                        'gamma': greeks.get('gamma'),
                        'theta': greeks.get('theta'),
                        'vega': greeks.get('vega')
                    }
                    # Add contract data
                    merged_data.update(matching_contract)
                    merged_array.append(merged_data)

    return merged_array

@router.post("/getOptionsChain")
async def get_options_chain(request: GetOptionsChainRequest):
    try:
        print("request",request)
        # Validate inputs
        if not request.symbol:
            raise HTTPException(status_code=400, detail="Please enter a symbol")
        if not request.date:
            raise HTTPException(status_code=400, detail="Please enter a date")
        if not request.optionType:
            raise HTTPException(status_code=400, detail="Please enter an option type")

        # Get API credentials
        api_key = os.getenv("ALPACA_OPTIONS_API_KEY")
        api_secret = os.getenv("ALPACA_OPTIONS_SECRET_KEY")

        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "APCA-API-KEY-ID": api_key ,
            "APCA-API-SECRET-KEY": api_secret
        }

        print("headers",headers)
        # Define URLs
        chain_url = f"https://data.alpaca.markets/v1beta1/options/snapshots/{request.symbol}?feed=indicative&limit=1000&type={request.optionType}&expiration_date={request.date}"
        contract_url = f"https://paper-api.alpaca.markets/v2/options/contracts?underlying_symbols={request.symbol}&status=active&expiration_date={request.date}&type={request.optionType}&limit=10000"
        quote_url = f"https://data.alpaca.markets/v2/stocks/{request.symbol}/quotes/latest"

        # Fetch data
        options_response = requests.get(chain_url, headers=headers)
        options_data = options_response.json()
        logger.info(f"Fetched options data for {options_data}")

        contract_response = requests.get(contract_url, headers=headers)
        contract_data = contract_response.json()
        logger.info(f"Fetched contract data for {contract_data}")

        quote_response = requests.get(quote_url, headers=headers)
        quote_data = quote_response.json()
        current_price = (quote_data['quote']['ap'] + quote_data['quote']['bp']) / 2
        logger.info(f"Current price for {request.symbol}: {current_price}")

        # Merge the data
        merged_data = merge_options_data(options_data, contract_data)
        
        return {
            "options_data": {"snapshots": merged_data},
            "current_price": current_price
        }

    except Exception as e:
        logger.error(f"Error fetching options data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

class BuyOptionsRequest(BaseModel):
    symbol: str
    amount: str

@router.post("/buyOptions")
async def buy_options(request: BuyOptionsRequest):
    try:
        api_key = os.getenv("ALPACA_OPTIONS_API_KEY")
        api_secret = os.getenv("ALPACA_OPTIONS_SECRET_KEY")
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "APCA-API-KEY-ID": api_key ,
            "APCA-API-SECRET-KEY": api_secret
        }

        url = f"https://paper-api.alpaca.markets/v2/orders"

        buy_payload = {
            "type": "market",
            "time_in_force": "day",
            "symbol": request.symbol,
            "qty": request.amount,  
            "side": "buy"
        }

        response = requests.post(url, headers=headers, json=buy_payload)
        print("response",response.json())
        return response.json()
        
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
