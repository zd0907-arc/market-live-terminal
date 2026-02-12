from fastapi import APIRouter, Query
from typing import List, Dict
from datetime import datetime
from backend.app.db.crud import get_sentiment_history

from backend.app.core.config import MOCK_DATA_DATE

router = APIRouter()

@router.get("/history")
def get_history(symbol: str = Query(...)):
    if MOCK_DATA_DATE:
        today_str = MOCK_DATA_DATE
    else:
        today_str = datetime.now().strftime("%Y-%m-%d")
        
    data = get_sentiment_history(symbol, today_str)
    return {
        "code": 200,
        "data": data
    }
