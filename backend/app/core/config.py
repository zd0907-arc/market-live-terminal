import os

# 动态获取项目根目录 (backend/app/core 的父级的父级的父级)
# 这样不论从哪里执行 python，都能唯一指向根目录下的 market_data.db
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
# 默认 DB 路径统一到 data/ 子目录，与 Docker 挂载路径对齐
DATA_DIR = os.path.join(ROOT_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_FILE = os.getenv("DB_PATH", os.path.join(DATA_DIR, "market_data.db"))
USER_DB_FILE = os.getenv("USER_DB_PATH", os.path.join(DATA_DIR, "user_data.db"))

# 模拟日期配置 (格式: YYYY-MM-DD)
# 设置此项后，所有数据读取接口将强制使用该日期，而不是 datetime.now()
# 方便收盘后或周末进行开发调试
MOCK_DATA_DATE = ""  # e.g., "2026-02-12"
