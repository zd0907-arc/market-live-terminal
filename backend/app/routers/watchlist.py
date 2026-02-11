from fastapi import APIRouter
from typing import List
from backend.app.models.schemas import WatchlistItem, APIResponse
from backend.app.db.crud import get_watchlist_items, add_watchlist_item
from backend.app.services.collector import collector
import threading

router = APIRouter()

@router.get("/watchlist", response_model=List[WatchlistItem])
def get_watchlist():
    return get_watchlist_items()

@router.post("/watchlist", response_model=APIResponse)
def add_watchlist(symbol: str, name: str):
    try:
        add_watchlist_item(symbol, name)
        # 立即触发一次抓取
        threading.Thread(target=lambda: collector._poll_watchlist()).start()
        return APIResponse(code=200, message="Added to watchlist")
    except Exception as e:
        return APIResponse(code=500, message=str(e))
