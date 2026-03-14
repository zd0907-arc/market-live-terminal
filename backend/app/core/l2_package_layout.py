import re
from pathlib import Path
from typing import Optional, Tuple


DAY_RE = re.compile(r"20\d{6}$")
MONTH_RE = re.compile(r"20\d{4}$")
SYMBOL_RE = re.compile(r"\d{6}\.(SZ|SH|BJ)$", re.IGNORECASE)


def is_month_dir_name(name: str) -> bool:
    return bool(MONTH_RE.fullmatch(name or ""))


def is_day_dir_name(name: str) -> bool:
    return bool(DAY_RE.fullmatch(name or ""))


def normalize_month_day_root(input_path: Path) -> Tuple[Path, str]:
    """
    Returns:
      (day_root, trade_date)

    Supported inputs:
      - D:/MarketData/202603/20260311
      - D:/MarketData/20260311
      - D:/MarketData/20260311/20260311
    """
    path = Path(input_path)
    if not path.exists() or not path.is_dir():
        raise ValueError(f"无效目录: {input_path}")

    name = path.name
    parent_name = path.parent.name

    if is_day_dir_name(name):
        nested_same_day = path / name
        if nested_same_day.is_dir():
            return nested_same_day, name
        if is_month_dir_name(parent_name):
            return path, name
        return path, name

    if is_symbol_dir(path):
        day_root = path.parent
        trade_date = day_root.name
        if not is_day_dir_name(trade_date):
            raise ValueError(f"无法从 symbol 目录推断交易日: {input_path}")
        return day_root, trade_date

    raise ValueError(f"无法识别的 L2 日包目录结构: {input_path}")


def is_symbol_dir(path: Path) -> bool:
    return path.is_dir() and bool(SYMBOL_RE.fullmatch(path.name))


def infer_trade_date_from_path(path: Path) -> Optional[str]:
    current = Path(path)
    for candidate in [current] + list(current.parents):
        if is_day_dir_name(candidate.name):
            return candidate.name
    return None

