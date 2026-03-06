from fastapi import APIRouter
from typing import List
from backend.app.models.schemas import WatchlistItem, APIResponse
from backend.app.db.crud import get_watchlist_items, add_watchlist_item, remove_watchlist_item
from backend.app.services.collector import collector
import threading
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/watchlist", response_model=List[WatchlistItem])
def get_watchlist():
    return get_watchlist_items()

@router.post("/watchlist", response_model=APIResponse)
def add_watchlist(symbol: str, name: str):
    try:
        add_watchlist_item(symbol, name)
        
        # 立即触发实时行情快照池拉取
        threading.Thread(target=lambda: collector._poll_watchlist()).start()
        
        # 并发触发：历史K线回落与散户情绪爬虫（独立线程防阻塞）
        try:
            from backend.app.services.sentiment_crawler import sentiment_crawler
            from backend.app.services.backfill import perform_historical_fetch
            
            # 手动模式调度，优先取最近几天快速出图
            threading.Thread(target=lambda: sentiment_crawler.run_crawl(symbol, mode="scheduler")).start()
            threading.Thread(target=lambda: perform_historical_fetch(symbol)).start()
        except Exception as bg_err:
            logger.error(f"Failed to trigger background workers for {symbol}: {bg_err}")

        return APIResponse(code=200, message="Added to watchlist, background syncing started")
    except Exception as e:
        return APIResponse(code=500, message=str(e))

@router.delete("/watchlist", response_model=APIResponse)
def delete_watchlist(symbol: str):
    """从星标列表中移除指定股票"""
    try:
        remove_watchlist_item(symbol)
        logger.info(f"Removed {symbol} from watchlist")
        return APIResponse(code=200, message=f"Removed {symbol} from watchlist")
    except Exception as e:
        logger.error(f"Failed to remove {symbol} from watchlist: {e}")
        return APIResponse(code=500, message=str(e))
