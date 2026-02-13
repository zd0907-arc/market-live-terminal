import re
import math
from typing import Dict, Any, Optional

from backend.app.db.crud import get_app_config

class StockSentimentCleaner:
    def __init__(self):
        # 1. 定义默认黑话词典 (支持正则)
        self.default_bull = [
            r'涨停', r'连板', r'跨年', r'龙头', r'满仓', r'梭哈', 
            r'起飞', r'大肉', r'接力', r'格局', r'封死', r'抢筹', r'牛逼', r'yyds'
        ]
        self.default_bear = [
            r'跌停', r'核按钮', r'大面', r'割肉', r'出货', r'垃圾', 
            r'骗炮', r'快跑', r'崩盘', r'A杀', r'埋了', r'套牢', r'退市', r'绿'
        ]
        
        self.reload_keywords()

    def reload_keywords(self):
        """
        从数据库加载关键词配置，支持热更新
        """
        config = get_app_config()
        
        # Load Bull Words
        bull_str = config.get('sentiment_bull_words', '')
        if bull_str:
            # Split by comma and strip
            custom_bull = [x.strip() for x in bull_str.split(',') if x.strip()]
            # Escape for regex safety if user inputs raw strings
            self.bull_patterns = [re.escape(x) for x in custom_bull]
        else:
            self.bull_patterns = self.default_bull
            
        # Load Bear Words
        bear_str = config.get('sentiment_bear_words', '')
        if bear_str:
            custom_bear = [x.strip() for x in bear_str.split(',') if x.strip()]
            self.bear_patterns = [re.escape(x) for x in custom_bear]
        else:
            self.bear_patterns = self.default_bear
            
        # Re-compile regex
        self.bull_regex = re.compile('|'.join(self.bull_patterns))
        self.bear_regex = re.compile('|'.join(self.bear_patterns))

    def parse_number(self, num_str: Any) -> int:
        """清洗数字，处理 '10万+' 这种格式"""
        if isinstance(num_str, (int, float)):
            return int(num_str)
        try:
            num_str = str(num_str).strip()
            if '万' in num_str:
                return int(float(num_str.replace('万', '').replace('+', '')) * 10000)
            return int(re.sub(r'\D', '', num_str) or 0) # 去除非数字字符
        except:
            return 0

    def calculate_sentiment(self, text: str) -> int:
        """
        计算情感分：-1 (空), 0 (中), 1 (多)
        不使用 LLM，纯规则匹配，毫秒级响应
        """
        if not text:
            return 0
            
        # 统计命中次数
        bull_hits = len(self.bull_regex.findall(text))
        bear_hits = len(self.bear_regex.findall(text))
        
        # 核心判定逻辑
        # 空头权重稍微大一点，因为A股散户跑得快
        score = bull_hits - (bear_hits * 1.2)
        
        if score > 0:
            return 1
        elif score < 0:
            return -1
        else:
            return 0

    def calculate_heat(self, read_count: Any, reply_count: Any) -> float:
        """
        计算热度权重
        公式：log(阅读) + 评论*20
        """
        r = self.parse_number(read_count)
        c = self.parse_number(reply_count)
        
        # 防止 log(0)
        read_score = math.log10(r + 1)
        # 评论的含金量是阅读的 20 倍
        reply_score = c * 20
        
        return round(read_score + reply_score, 2)

    def process_item(self, raw_item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        ETL 主入口：输入原始数据 -> 输出清洗后的数据
        """
        clean_item = raw_item.copy()
        
        # 1. 过滤广告/垃圾 (简单规则)
        text = raw_item.get('content', '')
        if not text or '加微' in text or '群' in text or len(text) < 2:
            return None # 丢弃该条数据
            
        # 2. 计算情感
        clean_item['sentiment_score'] = self.calculate_sentiment(text)
        
        # 3. 计算热度
        clean_item['heat_score'] = self.calculate_heat(
            raw_item.get('read_count', 0),
            raw_item.get('reply_count', 0)
        )
        
        # 清洗数字字段
        clean_item['read_count'] = self.parse_number(raw_item.get('read_count', 0))
        clean_item['reply_count'] = self.parse_number(raw_item.get('reply_count', 0))
        
        return clean_item

sentiment_analyzer = StockSentimentCleaner()
