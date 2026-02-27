from pydantic import BaseModel, Field
from typing import List, Optional

class TradeTick(BaseModel):
    symbol: str
    time: str
    price: float
    volume: int
    amount: float
    type: str
    date: str

class SentimentSnapshot(BaseModel):
    symbol: str
    timestamp: str
    date: str
    cvd: float
    oib: float
    signals: str
    bid1_vol: int
    ask1_vol: int
    tick_vol: int

class History30m(BaseModel):
    symbol: str
    start_time: str
    net_inflow: float
    main_buy: float
    main_sell: float
    super_net: float
    super_buy: float
    super_sell: float
    close: float
    open: float
    high: float
    low: float

class IngestTicksRequest(BaseModel):
    token: str = Field(..., description="Authentication token")
    ticks: List[TradeTick]
    history_30m: Optional[List[History30m]] = None

class IngestSnapshotsRequest(BaseModel):
    token: str = Field(..., description="Authentication token")
    snapshots: List[SentimentSnapshot]
