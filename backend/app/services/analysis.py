import logging
from backend.app.db.crud import get_app_config, get_ticks_for_aggregation, save_local_history
from datetime import datetime

logger = logging.getLogger(__name__)

def perform_aggregation(symbol: str, date: str = None):
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
        
    config = get_app_config()
    super_threshold = float(config.get('super_large_threshold', 1000000))
    large_threshold = float(config.get('large_threshold', 200000))
    config_sig = f"{int(super_threshold)}_{int(large_threshold)}"
    
    ticks = get_ticks_for_aggregation(symbol, date)
    
    if not ticks:
        return {"code": 404, "message": "No tick data found for aggregation"}
        
    main_buy = 0.0
    main_sell = 0.0
    total_vol = 0.0
    close_price = ticks[-1][2] if ticks else 0
    
    for amount, t_type, price in ticks:
        total_vol += amount
        is_main = amount >= large_threshold 
        
        if is_main:
            if t_type == '买盘':
                main_buy += amount
            elif t_type == '卖盘':
                main_sell += amount
                
    net_inflow = main_buy - main_sell
    activity_ratio = ((main_buy + main_sell) / total_vol * 100) if total_vol > 0 else 0
    
    save_local_history(symbol, date, net_inflow, main_buy, main_sell, close_price, 0, activity_ratio, config_sig)
    
    return {
        "code": 200, 
        "data": {
            "date": date,
            "net_inflow": net_inflow,
            "activity_ratio": activity_ratio,
            "config": config_sig
        }
    }
