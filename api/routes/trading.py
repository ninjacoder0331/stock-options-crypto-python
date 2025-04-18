from fastapi import APIRouter, HTTPException, Request, Header, Depends
from ..models.trader import TraderCreate, Trader
from bson import ObjectId
from passlib.context import CryptContext # type: ignore
import jwt # type: ignore
import os
from pydantic import BaseModel
from typing import Optional
from  ..database import get_database
from dotenv import load_dotenv
import logging
from datetime import datetime
import requests
import asyncio
import ntplib
from zoneinfo import ZoneInfo
from ..globals import buyPrice, update_buy_price


load_dotenv()

router = APIRouter()
logger = logging.getLogger(__name__)

async def get_settings():
    try:
        settings_collection = await get_database("settings")
        settings = await settings_collection.find_one({})
        return settings
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def current_time():
    try :
        ntp_client = ntplib.NTPClient()
        response = ntp_client.request('pool.ntp.org')
        currentTime = datetime.fromtimestamp(response.tx_time, ZoneInfo("America/New_York"))
        return currentTime.strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


