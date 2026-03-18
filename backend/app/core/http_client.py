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
    def get_market_context() -> dict:
        """
        返回当前中国市场状态与默认展示语义。
        目标：
        - 明确区分：盘前 / 盘中 / 午间休市 / 盘后 / 休盘日
        - 明确默认展示：今日数据 or 上一交易日数据
        - 明确默认是否应走实时路径
        """
        now = MarketClock._now_china()
        today_str = now.strftime("%Y-%m-%d")
        current_time = now.time()
        is_trade_day = TradeCalendar.is_trade_day(today_str)

        if not is_trade_day:
            default_display_date = TradeCalendar.get_last_trading_day(now)
            return {
                "natural_today": today_str,
                "is_trade_day": False,
                "market_status": "closed_day",
                "market_status_label": "休盘日",
                "default_display_date": default_display_date,
                "default_display_scope": "previous_trade_day",
                "default_display_scope_label": "默认展示上一交易日数据",
                "should_use_realtime_path": False,
            }

        pre_open_end = time(9, 15)
        morning_end = time(11, 30)
        afternoon_start = time(13, 0)
        session_close = time(15, 0)

        if current_time < pre_open_end:
            default_display_date = TradeCalendar.get_last_trading_day(now - timedelta(days=1))
            return {
                "natural_today": today_str,
                "is_trade_day": True,
                "market_status": "pre_open",
                "market_status_label": "盘前未开盘",
                "default_display_date": default_display_date,
                "default_display_scope": "previous_trade_day",
                "default_display_scope_label": "默认展示上一交易日数据",
                "should_use_realtime_path": False,
            }

        if pre_open_end <= current_time < morning_end:
            return {
                "natural_today": today_str,
                "is_trade_day": True,
                "market_status": "trading",
                "market_status_label": "盘中交易",
                "default_display_date": today_str,
                "default_display_scope": "today",
                "default_display_scope_label": "默认展示今日实时数据",
                "should_use_realtime_path": True,
            }

        if morning_end <= current_time < afternoon_start:
            return {
                "natural_today": today_str,
                "is_trade_day": True,
                "market_status": "lunch_break",
                "market_status_label": "午间休市",
                "default_display_date": today_str,
                "default_display_scope": "today",
                "default_display_scope_label": "默认展示今日已采集数据",
                "should_use_realtime_path": False,
            }

        if afternoon_start <= current_time <= session_close:
            return {
                "natural_today": today_str,
                "is_trade_day": True,
                "market_status": "trading",
                "market_status_label": "盘中交易",
                "default_display_date": today_str,
                "default_display_scope": "today",
                "default_display_scope_label": "默认展示今日实时数据",
                "should_use_realtime_path": True,
            }

        return {
            "natural_today": today_str,
            "is_trade_day": True,
            "market_status": "post_close",
            "market_status_label": "盘后复盘",
            "default_display_date": today_str,
            "default_display_scope": "today",
            "default_display_scope_label": "默认展示今日收盘后数据",
            "should_use_realtime_path": False,
        }

    @staticmethod
    def get_display_date() -> str:
        """
        获取前端应该展示的数据日期。
        - 如果是交易中: 返回今日
        - 如果是休市(晚上/周末/节假日): 返回最近的一个有效交易日
        """
        context = MarketClock.get_market_context()
        logger.info(
            "MarketClock.get_display_date => status=%s display_date=%s scope=%s",
            context["market_status"],
            context["default_display_date"],
            context["default_display_scope"],
        )
        return str(context["default_display_date"])

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
