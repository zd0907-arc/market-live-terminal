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
    [Legacy] Tell the backend that the user is currently viewing this symbol.
    """
    monitor.set_active_symbol(symbol)
    return APIResponse(code=200, message=f"Focus set to {symbol}")

@router.post("/unfocus", response_model=APIResponse)
def unfocus_symbol():
    """
    [Legacy] Tell the backend that the user left the detail view.
    """
    monitor.set_active_symbol(None)
    return APIResponse(code=200, message="Focus cleared")

@router.post("/heartbeat", response_model=APIResponse)
def register_heartbeat(symbol: str = Query(...), mode: str = Query("warm")):
    """
    [V4] Register a frontend heartbeat for a symbol with watch mode.
    """
    from backend.app.services.monitor import heartbeat_registry
    heartbeat_registry.register_heartbeat(symbol, mode)
    normalized_mode = "focus" if mode == "focus" else "warm"
    return APIResponse(code=200, message=f"Heartbeat registered for {symbol} [{normalized_mode}]")

@router.get("/active_symbols", response_model=APIResponse)
def get_active_symbols():
    """
    [V4] Get active symbols split by focus/warm tiers.
    Used by the Windows crawler to determine high-frequency vs baseline fetching.
    """
    from backend.app.services.monitor import heartbeat_registry
    active_symbols = heartbeat_registry.get_active_snapshot()
    return APIResponse(code=200, data=active_symbols)

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
