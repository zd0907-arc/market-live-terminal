import os
from typing import List

# 动态获取项目根目录 (backend/app/core 的父级的父级的父级)
# 这样不论从哪里执行 python，都能唯一指向根目录下的 market_data.db
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
# 默认优先使用本机正式数据目录，其次回退到 repo/data
DEFAULT_FORMAL_MARKET_DATA_ROOT = "/Users/dong/Desktop/AIGC/market-data"
DEFAULT_REPO_DATA_DIR = os.path.join(ROOT_DIR, "data")
DATA_DIR = os.getenv(
    "DATA_DIR",
    DEFAULT_FORMAL_MARKET_DATA_ROOT if os.path.isdir(DEFAULT_FORMAL_MARKET_DATA_ROOT) else DEFAULT_REPO_DATA_DIR,
)
os.makedirs(DATA_DIR, exist_ok=True)
DB_FILE = os.getenv("DB_PATH", os.path.join(DATA_DIR, "market_data.db"))
USER_DB_FILE = os.getenv("USER_DB_PATH", os.path.join(DATA_DIR, "user_data.db"))
ATOMIC_FACTS_DIR = os.getenv("ATOMIC_FACTS_DIR", os.path.join(DATA_DIR, "atomic_facts"))
DEFAULT_ATOMIC_COMPACT_DB_FILE = os.path.join(ATOMIC_FACTS_DIR, "market_atomic_mainboard_compact_current.db")
DEFAULT_ATOMIC_MAINBOARD_DB_FILE = DEFAULT_ATOMIC_COMPACT_DB_FILE
DEFAULT_ATOMIC_DB_FILE = os.path.join(ATOMIC_FACTS_DIR, "market_atomic.db")
ATOMIC_MAINBOARD_DB_PATH = os.getenv("ATOMIC_MAINBOARD_DB_PATH", DEFAULT_ATOMIC_MAINBOARD_DB_FILE)
ATOMIC_DB_PATH = os.getenv("ATOMIC_DB_PATH", DEFAULT_ATOMIC_DB_FILE)
ATOMIC_COMPACT_DB_PATH = os.getenv("ATOMIC_COMPACT_DB_PATH", DEFAULT_ATOMIC_COMPACT_DB_FILE)


def _env_flag(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in {"1", "true", "yes", "on"}


# 模拟日期配置 (格式: YYYY-MM-DD)
# 设置此项后，所有数据读取接口将强制使用该日期，而不是 datetime.now()
# 方便收盘后或周末进行开发调试
MOCK_DATA_DATE = ""  # e.g., "2026-02-12"


def candidate_atomic_db_paths() -> List[str]:
    # 测试/临时环境经常只注入 DB_PATH 指向一个空的 tmp db。
    # 这种情况下如果继续回退到本机正式 atomic 库，会让单元测试或临时服务混入真实数据。
    # 正式本地研究站会显式注入 ATOMIC_*，直接启动且无 DB_PATH 时才使用默认 atomic 路径。
    # 当前默认正式底座是 compact；legacy full_reverse 不再作为隐式候选。
    compact_candidates = []
    compact_path = ATOMIC_COMPACT_DB_PATH.strip()
    if _env_flag("ENABLE_ATOMIC_COMPACT_READ") and compact_path:
        compact_candidates.append(compact_path)
    if (
        os.getenv("DB_PATH")
        and not os.getenv("ATOMIC_DB_PATH")
        and not os.getenv("ATOMIC_MAINBOARD_DB_PATH")
        and not compact_candidates
    ):
        return []
    candidates = [
        *compact_candidates,
        os.getenv("ATOMIC_DB_PATH", ""),
        os.getenv("ATOMIC_MAINBOARD_DB_PATH", ""),
        ATOMIC_MAINBOARD_DB_PATH,
        ATOMIC_DB_PATH,
        DEFAULT_ATOMIC_DB_FILE,
    ]
    out: List[str] = []
    seen = set()
    for raw in candidates:
        path = str(raw or "").strip()
        if not path or path in seen:
            continue
        seen.add(path)
        out.append(path)
    return out
