import os

# 动态获取项目根目录 (backend/app/core 的父级的父级的父级)
# 这样不论从哪里执行 python，都能唯一指向根目录下的 market_data.db
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
# 允许通过环境变量配置数据库路径，默认为根目录的 market_data.db
DB_FILE = os.getenv("DB_PATH", os.path.join(ROOT_DIR, "market_data.db"))

# 模拟日期配置 (格式: YYYY-MM-DD)
# 设置此项后，所有数据读取接口将强制使用该日期，而不是 datetime.now()
# 方便收盘后或周末进行开发调试
MOCK_DATA_DATE = ""  # e.g., "2026-02-12"
