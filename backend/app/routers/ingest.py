from fastapi import APIRouter, HTTPException
import os
import logging
from collections import defaultdict
from backend.app.models.ingest_models import IngestTicksRequest, IngestSnapshotsRequest
from backend.app.db.crud import (
    save_sentiment_snapshot,
    save_history_30m_batch,
    save_ticks_daily_overwrite,
)

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
        # Windows 节点上传的是“当日全量 tick 快照”，按 symbol+date 覆盖写可避免重复累加
        if request.ticks:
            grouped_ticks = defaultdict(list)
            for t in request.ticks:
                grouped_ticks[(t.symbol, t.date)].append(
                    (t.symbol, t.time, t.price, t.volume, t.amount, t.type, t.date)
                )

            total_saved = 0
            for (symbol, date_str), rows in grouped_ticks.items():
                save_ticks_daily_overwrite(symbol, date_str, rows)
                total_saved += len(rows)
            logger.info(
                f"[Ingest] Overwrote ticks: payload={len(request.ticks)}, saved={total_saved}, groups={len(grouped_ticks)}."
            )
            
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
        if not request.snapshots:
            return {"status": "success", "message": "Ingested 0 snapshots"}

        rows = [
            (
                s.symbol,
                s.timestamp,
                s.date,
                s.cvd,
                s.oib,
                0.0,   # price: ingest payload未包含，保留默认值
                0,     # outer_vol
                0,     # inner_vol
                s.signals,
                s.bid1_vol,
                s.ask1_vol,
                s.tick_vol
            )
            for s in request.snapshots
        ]
        save_sentiment_snapshot(rows)
        
        logger.info(f"[Ingest] Saved {len(rows)} snapshots.")
        return {"status": "success", "message": f"Ingested {len(rows)} snapshots"}
        
    except Exception as e:
        logger.error(f"[Ingest Snapshots Error]: {e}")
        raise HTTPException(status_code=500, detail=str(e))
