import sys
import os
import logging

# Ensure backend can be imported
sys.path.append(os.getcwd())

from backend.app.db.crud import update_app_config

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Expanded Keywords based on 1000+ comment mining
BULL_WORDS = [
    "涨停", "连板", "跨年", "龙头", "满仓", "梭哈", "起飞", "大肉", "接力", "格局", 
    "封死", "抢筹", "牛逼", "yyds", "红包", "吃肉", "上车", "倒车接人", "启动", 
    "稳了", "抄底", "回本", "解套", "飞天", "主升浪", "打板", "大阳", "捡钱", 
    "数板", "信创", "新高", "翻倍"
]

BEAR_WORDS = [
    "跌停", "核按钮", "大面", "割肉", "出货", "垃圾", "骗炮", "快跑", "崩盘", "A杀", 
    "埋了", "套牢", "退市", "绿", "跳水", "阴跌", "织布", "压盘", "砸盘", "诱多", 
    "杀猪", "接盘", "跑路", "凉凉", "恶心", "腰斩", "完蛋", "挂了", "无论", "死猪",
    "瀑布", "骗子", "清仓", "亏损"
]

def main():
    logger.info("Updating sentiment keywords in database...")
    
    bull_str = ", ".join(BULL_WORDS)
    bear_str = ", ".join(BEAR_WORDS)
    
    try:
        update_app_config('sentiment_bull_words', bull_str)
        logger.info(f"Updated Bull Words ({len(BULL_WORDS)}): {bull_str[:50]}...")
        
        update_app_config('sentiment_bear_words', bear_str)
        logger.info(f"Updated Bear Words ({len(BEAR_WORDS)}): {bear_str[:50]}...")
        
        logger.info("Successfully updated sentiment configuration!")
        
    except Exception as e:
        logger.error(f"Failed to update config: {e}")

if __name__ == "__main__":
    main()
