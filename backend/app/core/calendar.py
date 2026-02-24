import logging
import requests
from datetime import datetime, timedelta
from typing import Set

logger = logging.getLogger(__name__)

class TradeCalendar:
    _trade_days: Set[str] = set()
    _initialized = False

    @classmethod
    def init(cls):
        """
        初始化交易日历
        从新浪财经获取上证指数(sh000001)的日K线日期，作为权威的交易日列表。
        """
        if cls._initialized:
            return

        try:
            # 获取最近365天的日K线日期
            url = "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData?symbol=sh000001&scale=240&ma=no&datalen=365"
            resp = requests.get(url, timeout=5)
            data = resp.json()
            
            if isinstance(data, list):
                for item in data:
                    day = item.get('day')
                    if day:
                        cls._trade_days.add(day)
                
                # Workaround for VM having a future date: Fill in missing weekdays up to today
                if cls._trade_days:
                    max_d_str = max(cls._trade_days)
                    max_d = datetime.strptime(max_d_str, "%Y-%m-%d")
                    now = datetime.now()
                    while max_d.date() < now.date():
                        max_d += timedelta(days=1)
                        if max_d.weekday() < 5:  # Weekday
                            cls._trade_days.add(max_d.strftime("%Y-%m-%d"))

                logger.info(f"TradeCalendar initialized with {len(cls._trade_days)} trading days.")
                cls._initialized = True
            else:
                logger.warning("Failed to fetch trade calendar: invalid response format")
                
        except Exception as e:
            logger.error(f"Failed to init TradeCalendar: {e}")
            # Fallback: do nothing, rely on empty set (logic will fail safe or use weekends)

    @classmethod
    def is_trade_day(cls, date_str: str) -> bool:
        """
        判断是否为交易日 (YYYY-MM-DD)
        """
        if not cls._initialized:
            # Fallback: simple weekend check
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                return dt.weekday() < 5
            except:
                return False
                
        return date_str in cls._trade_days

    @classmethod
    def get_last_trading_day(cls, base_date: datetime = None) -> str:
        """
        获取最近的一个交易日 (不包含今天，或者包含今天如果今天已收盘?)
        策略: 从 base_date 开始往前推，直到找到一个在 _trade_days 里的日期。
        """
        if not base_date:
            base_date = datetime.now()
            
        curr = base_date
        # 最多往前推30天，防止死循环
        for _ in range(30):
            d_str = curr.strftime("%Y-%m-%d")
            if cls.is_trade_day(d_str):
                return d_str
            curr -= timedelta(days=1)
            
        # Fallback
        return base_date.strftime("%Y-%m-%d")

    @classmethod
    def get_last_n_trading_days(cls, n: int) -> list[str]:
        """
        获取最近的 N 个交易日 (倒序: 最近的在前面)
        """
        days = []
        curr = datetime.now()
        
        # 简单防死循环
        for _ in range(n * 5): 
            d_str = curr.strftime("%Y-%m-%d")
            if cls.is_trade_day(d_str):
                days.append(d_str)
                if len(days) >= n:
                    break
            curr -= timedelta(days=1)
            
        return days
