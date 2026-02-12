from fastapi import APIRouter, Query
from typing import List, Dict
from datetime import datetime
from backend.app.db.crud import get_sentiment_history

router = APIRouter()

@router.get("/history")
def get_history(symbol: str = Query(...)):
    today_str = datetime.now().strftime("%Y-%m-%d")
    data = get_sentiment_history(symbol, today_str)
    return {
        "code": 200,
        "data": data
    }
