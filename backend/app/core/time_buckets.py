from datetime import datetime, time


CANONICAL_30M_STARTS = (
    "09:30:00",
    "10:00:00",
    "10:30:00",
    "11:00:00",
    "13:00:00",
    "13:30:00",
    "14:00:00",
    "14:30:00",
)


def map_to_30m_bucket_start(dt: datetime):
    t = dt.time()

    if time(9, 30) <= t < time(10, 0):
        return dt.replace(hour=9, minute=30, second=0, microsecond=0)
    if time(10, 0) <= t < time(10, 30):
        return dt.replace(hour=10, minute=0, second=0, microsecond=0)
    if time(10, 30) <= t < time(11, 0):
        return dt.replace(hour=10, minute=30, second=0, microsecond=0)
    if time(11, 0) <= t < time(11, 30):
        return dt.replace(hour=11, minute=0, second=0, microsecond=0)

    if time(13, 0) <= t < time(13, 30):
        return dt.replace(hour=13, minute=0, second=0, microsecond=0)
    if time(13, 30) <= t < time(14, 0):
        return dt.replace(hour=13, minute=30, second=0, microsecond=0)
    if time(14, 0) <= t < time(14, 30):
        return dt.replace(hour=14, minute=0, second=0, microsecond=0)
    if time(14, 30) <= t <= time(15, 0):
        return dt.replace(hour=14, minute=30, second=0, microsecond=0)

    return None


def is_canonical_30m_start(start_time_str: str):
    if " " not in start_time_str:
        return False
    return start_time_str.split(" ", 1)[1] in CANONICAL_30M_STARTS
