import logging
import asyncio
import httpx
from datetime import datetime, time, timedelta, timezone
from fake_useragent import UserAgent
from backend.app.core.calendar import TradeCalendar

logger = logging.getLogger(__name__)
CHINA_TZ = timezone(timedelta(hours=8))

class MarketClock:
    """
    负责交易时间判断
    规则：
    1. 非交易日 (节假日/周末) 不交易
    2. 交易日 09:15-11:30, 13:00-15:05 允许运行
    """
    @staticmethod
    def _now_china() -> datetime:
        return datetime.now(timezone.utc).astimezone(CHINA_TZ)

    @staticmethod
    def is_trading_time() -> bool:
        now = MarketClock._now_china()
        today_str = now.strftime("%Y-%m-%d")
        
        # 1. 交易日检查 (使用 TradeCalendar)
        if not TradeCalendar.is_trade_day(today_str):
            return False
            
        # 2. 时间段检查
        current_time = now.time()
        
        # 上午盘 (含集合竞价)
        morning_start = time(9, 15)
        morning_end = time(11, 30)
        
        # 下午盘
        afternoon_start = time(13, 0)
        afternoon_end = time(15, 5) # 多给5分钟收尾
        
        is_morning = morning_start <= current_time <= morning_end
        is_afternoon = afternoon_start <= current_time <= afternoon_end
        
        result = is_morning or is_afternoon
        if not result:
            logger.info(f"MarketClock.is_trading_time: False | Now={current_time} | Morn=[{morning_start}-{morning_end}] | Aft=[{afternoon_start}-{afternoon_end}]")
            
        return result

    @staticmethod
    def get_display_date() -> str:
        """
        获取前端应该展示的数据日期。
        - 如果是交易中: 返回今日
        - 如果是休市(晚上/周末/节假日): 返回最近的一个有效交易日
        """
        now = MarketClock._now_china()
        today_str = now.strftime("%Y-%m-%d")
        
        logger.info(f"DEBUG: Checking display date. Today={today_str}, Weekday={now.weekday()}, IsTradeDay={TradeCalendar.is_trade_day(today_str)}")
        
        # 如果今天是交易日
        if TradeCalendar.is_trade_day(today_str):
            # 如果还没开盘 (09:15之前)，显示昨天
            if now.time() < time(9, 15):
                return TradeCalendar.get_last_trading_day(now - timedelta(days=1))
            # 否则显示今天 (盘中或盘后)
            return today_str
            
        # 如果今天不是交易日，找最近的一天
        last_day = TradeCalendar.get_last_trading_day(now)
        logger.info(f"DEBUG: Not a trade day. Fallback to {last_day}")
        return last_day

class HTTPClient:
    """
    封装带有随机 User-Agent 的 HTTP 客户端
    """
    _ua = UserAgent()
    
    @classmethod
    async def get(cls, url: str, params: dict = None, timeout: float = 10.0):
        headers = {
            "User-Agent": cls._ua.random,
            "Accept": "*/*",
            "Connection": "keep-alive"
        }
        
        async with httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=True) as client:
            try:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response
            except Exception as e:
                logger.error(f"HTTP Request Failed [{url}]: {e}")
                return None
