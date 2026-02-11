from fastapi import APIRouter
from backend.app.models.schemas import APIResponse, AggregateResult
from backend.app.services.market import get_sina_money_flow, get_sina_kline
from backend.app.services.analysis import perform_aggregation
from backend.app.db.crud import get_local_history_data, get_app_config
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/aggregate", response_model=APIResponse)
def aggregate_history(symbol: str, date: str = None):
    """
    根据当前配置的阈值，将指定日期(默认今日)的逐笔数据聚合为历史分析记录
    """
    result = perform_aggregation(symbol, date)
    return APIResponse(**result)

@router.get("/history/local")
def get_local_history(symbol: str):
    config = get_app_config()
    super_threshold = float(config.get('super_large_threshold', 1000000))
    large_threshold = float(config.get('large_threshold', 200000))
    config_sig = f"{int(super_threshold)}_{int(large_threshold)}"
    
    rows = get_local_history_data(symbol, config_sig)
    
    data = []
    for r in rows:
        data.append({
            "date": r[1],
            "net_inflow": r[2],
            "main_buy_amount": r[3],
            "main_sell_amount": r[4],
            "close": r[5],
            "change_pct": r[6],
            "activityRatio": r[7],
            "buyRatio": (r[3] / (r[3]+r[4]+1) * 100) if (r[3]+r[4]) > 0 else 0,
            "sellRatio": (r[4] / (r[3]+r[4]+1) * 100) if (r[3]+r[4]) > 0 else 0
        })
    return data

@router.get("/history_analysis")
async def get_history_analysis(symbol: str, source: str = "sina"):
    """
    核心聚合接口：合并资金流向与K线行情
    """
    if source == "local":
        data = get_local_history(symbol)
        return APIResponse(code=200, data=data)

    try:
        if not symbol or not symbol.startswith(("sh", "sz", "bj")):
            return APIResponse(code=400, message="Invalid symbol format")

        flows = await get_sina_money_flow(symbol)
        if not flows:
            return APIResponse(code=200, data=[])

        kline_map = await get_sina_kline(symbol)
        logger.info(f"DEBUG: get_sina_kline returned {len(kline_map)} items")
        result = []
        
        for item in flows:
            try:
                if not isinstance(item, dict): continue
                date = item.get('opendate') or item.get('date')
                if not date: continue
            
                def safe_float(val):
                    if val is None or val == "": return 0.0
                    try: return float(val)
                    except: return 0.0

                r0 = safe_float(item.get('r0'))
                r0_net = safe_float(item.get('r0_net'))
                r1 = safe_float(item.get('r1'))
                r1_net = safe_float(item.get('r1_net'))
                
                r0_in = (r0 + r0_net) / 2
                r0_out = (r0 - r0_net) / 2
                r1_in = (r1 + r1_net) / 2
                r1_out = (r1 - r1_net) / 2
                
                main_buy = r0_in + r1_in
                main_sell = r0_out + r1_out
                
                k_info = kline_map.get(date, {})
                total_amount = k_info.get('amount', 0)
                close_price = k_info.get('close', 0)
                if close_price == 0:
                     close_price = safe_float(item.get('trade'))

                if total_amount <= 0:
                    r2 = safe_float(item.get('r2'))
                    r3 = safe_float(item.get('r3'))
                    total_amount = r0 + r1 + r2 + r3
                    if total_amount == 0: total_amount = 1.0

                buyRatio = (main_buy / total_amount * 100) if total_amount > 0 else 0
                sellRatio = (main_sell / total_amount * 100) if total_amount > 0 else 0
                activityRatio = ((main_buy + main_sell) / total_amount * 100) if total_amount > 0 else 0

                # Calculate Super Large Ratio (r0 / Total)
                super_large_total = r0
                super_large_ratio = (super_large_total / total_amount * 100) if total_amount > 0 else 0

                result.append({
                    "date": date,
                    "close": close_price,
                    "total_amount": total_amount,
                    "main_buy_amount": main_buy,
                    "main_sell_amount": main_sell,
                    "net_inflow": main_buy - main_sell,
                    "super_large_in": r0_in,
                    "super_large_out": r0_out,
                    "buyRatio": buyRatio,
                    "sellRatio": sellRatio,
                    "activityRatio": activityRatio,
                    "super_large_ratio": super_large_ratio
                })
            except Exception as inner_e:
                logger.warning(f"Error parsing item: {inner_e}")
                continue

        result.sort(key=lambda x: x['date'])
        return APIResponse(code=200, data=result)
        
    except Exception as e:
        logger.error(f"Global Endpoint Error: {e}")
        return APIResponse(code=500, message=str(e), data=[])
