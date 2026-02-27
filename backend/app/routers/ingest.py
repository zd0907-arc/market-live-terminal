from fastapi import APIRouter, HTTPException, Depends
from typing import List
import os
import logging
from backend.app.models.ingest_models import IngestTicksRequest, IngestSnapshotsRequest
from backend.app.db.crud import save_trade_ticks, save_sentiment_snapshot, save_history_30m_batch

router = APIRouter()
logger = logging.getLogger(__name__)

def verify_token(token: str):
    expected_token = os.getenv("INGEST_TOKEN", "zhangdata-secret-token")
    if token != expected_token:
        raise HTTPException(status_code=401, detail="Invalid ingestion token")

@router.post("/ticks")
async def ingest_ticks(request: IngestTicksRequest):
    """
    接收来自 Windows 节点的 Trade Ticks 与即时 30m K线重算结果
    """
    verify_token(request.token)
    
    try:
        # 转换 Pydantic model 到 Tuple 列表，适配 CRUD 函数
        # save_trade_ticks expects list of tuples: (symbol, time, price, volume, amount, type, date)
        if request.ticks:
            ticks_data = [
                (t.symbol, t.time, t.price, t.volume, t.amount, t.type, t.date)
                for t in request.ticks
            ]
            save_trade_ticks(ticks_data)
            logger.info(f"[Ingest] Saved {len(ticks_data)} ticks.")
            
        if request.history_30m:
            # save_history_30m_batch expects list of dicts directly
            h30m_data = [h.dict() for h in request.history_30m]
            save_history_30m_batch(h30m_data)
            logger.info(f"[Ingest] Saved {len(h30m_data)} 30m history bars.")

        return {"status": "success", "message": f"Ingested {len(request.ticks)} ticks"}
        
    except Exception as e:
        logger.error(f"[Ingest Ticks Error]: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/snapshots")
async def ingest_snapshots(request: IngestSnapshotsRequest):
    """
    接收来自 Windows 节点的实时高频 Sentiment Snapshots
    """
    verify_token(request.token)
    
    try:
        # save_sentiment_snapshot 内部有容错与 ignore，因此可以并发插入
        inserted = 0
        for s in request.snapshots:
            try:
                save_sentiment_snapshot(
                    symbol=s.symbol,
                    cvd=s.cvd,
                    oib=s.oib,
                    signals_json=s.signals,
                    bid_vol=s.bid1_vol,
                    ask_vol=s.ask1_vol,
                    tick_vol=s.tick_vol
                )
                inserted += 1
            except Exception as e:
                logger.warning(f"Ingest snapshot ignore DB conflict: {e}")
                
        logger.info(f"[Ingest] Processed {len(request.snapshots)} snapshots.")
        return {"status": "success", "message": f"Ingested {inserted} snapshots"}
        
    except Exception as e:
        logger.error(f"[Ingest Snapshots Error]: {e}")
        raise HTTPException(status_code=500, detail=str(e))
