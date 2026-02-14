from fastapi import APIRouter, Query, Body
from typing import List, Dict
from datetime import datetime
from backend.app.db.crud import get_sentiment_history
from backend.app.services.monitor import monitor
from backend.app.models.schemas import APIResponse

from backend.app.core.config import MOCK_DATA_DATE

router = APIRouter()

@router.post("/focus", response_model=APIResponse)
def focus_symbol(symbol: str = Body(..., embed=True)):
    """
    Tell the backend that the user is currently viewing this symbol.
    The monitor service will promote this symbol to the HOT queue (high freq).
    """
    monitor.set_active_symbol(symbol)
    return APIResponse(code=200, message=f"Focus set to {symbol}")

@router.post("/unfocus", response_model=APIResponse)
def unfocus_symbol():
    """
    Tell the backend that the user left the detail view.
    The monitor service will stop high freq polling for the active symbol.
    """
    monitor.set_active_symbol(None)
    return APIResponse(code=200, message="Focus cleared")

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
