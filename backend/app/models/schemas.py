from pydantic import BaseModel
from typing import List, Optional, Union

# --- Base Response ---
class APIResponse(BaseModel):
    code: int
    message: Optional[str] = None
    data: Optional[Union[dict, list, str]] = None

# --- Watchlist ---
class WatchlistItem(BaseModel):
    symbol: str
    name: str
    added_at: str

# --- Market Data ---
class TickData(BaseModel):
    time: str
    price: float
    volume: int
    amount: float
    type: str

class MarketSnapshot(BaseModel):
    price: float
    change: float
    volume: float
    time: str

class VerifyResult(BaseModel):
    tencent: Optional[MarketSnapshot]
    eastmoney: Optional[MarketSnapshot]

# --- Config ---
class AppConfig(BaseModel):
    large_threshold: float
    super_large_threshold: float

# --- Analysis ---
class HistoryAnalysisItem(BaseModel):
    date: str
    net_inflow: float
    main_buy_amount: float
    main_sell_amount: float
    close: float
    change_pct: float
    activityRatio: float
    buyRatio: float
    sellRatio: float
    total_amount: Optional[float] = 0
    super_large_in: Optional[float] = 0
    super_large_out: Optional[float] = 0

class AggregateResult(BaseModel):
    date: str
    net_inflow: float
    activity_ratio: float
    config: str
