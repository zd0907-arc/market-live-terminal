import os
from typing import List

# 动态获取项目根目录 (backend/app/core 的父级的父级的父级)
# 这样不论从哪里执行 python，都能唯一指向根目录下的 market_data.db
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DEFAULT_FORMAL_MARKET_DATA_ROOT = os.getenv(
    "FORMAL_MARKET_DATA_ROOT",
    "/Users/dong/Desktop/AIGC/market-data",
)


def _first_existing_dir(*candidates: str) -> str:
    for candidate in candidates:
        path = str(candidate or "").strip()
        if path and os.path.isdir(path):
            return path
    return ""


def _first_nonempty(*candidates: str) -> str:
    for candidate in candidates:
        path = str(candidate or "").strip()
        if path:
            return path
    return ""


def _parent_dir(path: str) -> str:
    text = str(path or "").strip()
    if not text:
        return ""
    return os.path.dirname(text)


def _research_root_from_db_path(path: str) -> str:
    parent = _parent_dir(path)
    if not parent:
        return ""
    leaf = os.path.basename(parent.rstrip(os.sep))
    if leaf in {"selection", "atomic_facts", "market_heat"}:
        return os.path.dirname(parent)
    return parent


def _derive_live_root_from_env_files() -> str:
    return _first_nonempty(
        _parent_dir(os.getenv("DB_PATH", "")),
        _parent_dir(os.getenv("USER_DB_PATH", "")),
    )


def _derive_research_root_from_env_files() -> str:
    return _first_nonempty(
        _research_root_from_db_path(os.getenv("SELECTION_DB_PATH", "")),
        _research_root_from_db_path(os.getenv("ATOMIC_MAINBOARD_DB_PATH", "")),
        _research_root_from_db_path(os.getenv("ATOMIC_COMPACT_DB_PATH", "")),
        _research_root_from_db_path(os.getenv("ATOMIC_DB_PATH", "")),
    )


def _resolve_default_data_dir() -> str:
    explicit = str(os.getenv("DATA_DIR", "")).strip()
    if explicit:
        return explicit
    explicit_research_root = _derive_research_root_from_env_files()
    if explicit_research_root:
        return explicit_research_root
    explicit_live_root = _derive_live_root_from_env_files()
    if explicit_live_root:
        return explicit_live_root
    formal_root = str(os.getenv("FORMAL_MARKET_DATA_ROOT", DEFAULT_FORMAL_MARKET_DATA_ROOT)).strip()
    research_root = str(os.getenv("RESEARCH_CURRENT_ROOT", "")).strip()
    live_root = str(os.getenv("LIVE_DATA_ROOT", "")).strip()
    if research_root:
        return research_root
    if live_root:
        return live_root
    derived_research = os.path.join(formal_root, "research", "current")
    derived_live = os.path.join(formal_root, "live")
    return _first_existing_dir(derived_research, formal_root, derived_live) or derived_research


def _resolve_live_data_root() -> str:
    explicit = str(os.getenv("LIVE_DATA_ROOT", "")).strip()
    if explicit:
        return explicit
    explicit_live_root = _derive_live_root_from_env_files()
    if explicit_live_root:
        return explicit_live_root
    if os.getenv("DATA_DIR"):
        return DATA_DIR
    if os.getenv("DB_PATH") or os.getenv("USER_DB_PATH"):
        return DATA_DIR
    formal_root = str(os.getenv("FORMAL_MARKET_DATA_ROOT", DEFAULT_FORMAL_MARKET_DATA_ROOT)).strip()
    derived_live = os.path.join(formal_root, "live")
    if os.path.isdir(derived_live):
        return derived_live
    if os.path.isfile(os.path.join(formal_root, "market_data.db")) or os.path.isfile(os.path.join(formal_root, "user_data.db")):
        return formal_root
    return derived_live


def _resolve_research_current_root() -> str:
    explicit = str(os.getenv("RESEARCH_CURRENT_ROOT", "")).strip()
    if explicit:
        return explicit
    explicit_research_root = _derive_research_root_from_env_files()
    if explicit_research_root:
        return explicit_research_root
    if os.getenv("DATA_DIR"):
        return DATA_DIR
    if os.getenv("SELECTION_DB_PATH") or os.getenv("ATOMIC_MAINBOARD_DB_PATH") or os.getenv("ATOMIC_COMPACT_DB_PATH"):
        return DATA_DIR
    formal_root = str(os.getenv("FORMAL_MARKET_DATA_ROOT", DEFAULT_FORMAL_MARKET_DATA_ROOT)).strip()
    derived_research = os.path.join(formal_root, "research", "current")
    if os.path.isdir(derived_research):
        return derived_research
    if os.path.isdir(os.path.join(formal_root, "selection")) or os.path.isdir(os.path.join(formal_root, "atomic_facts")):
        return formal_root
    return derived_research


DATA_DIR = _resolve_default_data_dir()
LIVE_DATA_ROOT = _resolve_live_data_root()
RESEARCH_CURRENT_ROOT = _resolve_research_current_root()

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LIVE_DATA_ROOT, exist_ok=True)
os.makedirs(RESEARCH_CURRENT_ROOT, exist_ok=True)

DB_FILE = os.getenv("DB_PATH", os.path.join(LIVE_DATA_ROOT, "market_data.db"))
USER_DB_FILE = os.getenv("USER_DB_PATH", os.path.join(LIVE_DATA_ROOT, "user_data.db"))
ATOMIC_FACTS_DIR = os.getenv("ATOMIC_FACTS_DIR", os.path.join(RESEARCH_CURRENT_ROOT, "atomic_facts"))
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


def _current_atomic_facts_dir() -> str:
    explicit = str(os.getenv("ATOMIC_FACTS_DIR", "")).strip()
    if explicit:
        return explicit
    derived_research_root = _derive_research_root_from_env_files()
    if derived_research_root:
        return os.path.join(derived_research_root, "atomic_facts")
    explicit_research_root = str(os.getenv("RESEARCH_CURRENT_ROOT", "")).strip()
    if explicit_research_root:
        return os.path.join(explicit_research_root, "atomic_facts")
    if os.getenv("DATA_DIR"):
        return os.path.join(DATA_DIR, "atomic_facts")
    return ATOMIC_FACTS_DIR


def candidate_atomic_db_paths() -> List[str]:
    # 测试/临时环境经常只注入 DB_PATH 指向一个空的 tmp db。
    # 这种情况下如果继续回退到本机正式 atomic 库，会让单元测试或临时服务混入真实数据。
    # 正式本地研究站会显式注入 ATOMIC_*，直接启动且无 DB_PATH 时才使用默认 atomic 路径。
    # 当前默认正式底座是 compact；legacy full_reverse 不再作为隐式候选。
    atomic_facts_dir = _current_atomic_facts_dir()
    default_compact_db_file = os.path.join(atomic_facts_dir, "market_atomic_mainboard_compact_current.db")
    default_mainboard_db_file = default_compact_db_file
    default_atomic_db_file = os.path.join(atomic_facts_dir, "market_atomic.db")

    env_atomic_db_path = str(os.getenv("ATOMIC_DB_PATH", "")).strip()
    env_mainboard_db_path = str(os.getenv("ATOMIC_MAINBOARD_DB_PATH", "")).strip()
    env_compact_db_path = str(os.getenv("ATOMIC_COMPACT_DB_PATH", "")).strip()

    compact_candidates = []
    if _env_flag("ENABLE_ATOMIC_COMPACT_READ"):
        compact_candidates.append(env_compact_db_path or default_compact_db_file)

    explicit_atomic_paths = any((env_atomic_db_path, env_mainboard_db_path, env_compact_db_path))
    if (
        os.getenv("DB_PATH")
        and not explicit_atomic_paths
        and not compact_candidates
    ):
        return []

    candidates = [
        *compact_candidates,
        env_atomic_db_path,
        env_mainboard_db_path,
        env_compact_db_path,
        default_mainboard_db_file,
        default_atomic_db_file,
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
