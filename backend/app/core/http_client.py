import logging
import asyncio
import httpx
from datetime import datetime, time
from fake_useragent import UserAgent

logger = logging.getLogger(__name__)

class MarketClock:
    """
    负责交易时间判断
    规则：
    1. 周末不交易
    2. 交易日 09:15-11:30, 13:00-15:05 允许运行
    """
    @staticmethod
    def is_trading_time() -> bool:
        now = datetime.now()
        
        # 1. 周末检查 (0=Mon, 6=Sun)
        if now.weekday() >= 5:
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
        
        return is_morning or is_afternoon

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
        
        async with httpx.AsyncClient(headers=headers, timeout=timeout) as client:
            try:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response
            except Exception as e:
                logger.error(f"HTTP Request Failed [{url}]: {e}")
                return None
