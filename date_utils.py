from __future__ import annotations

from datetime import datetime, timedelta


def add_months_same_day(dt: datetime, months: int = 1) -> datetime:
    """
    按“同日下个月”计算：1/7 -> 2/7。
    若目标月没有该日期，则取该月最后一天（例如 1/31 -> 2/28 或 2/29）。
    """
    if months == 0:
        return dt

    year = dt.year
    month = dt.month + months
    year += (month - 1) // 12
    month = (month - 1) % 12 + 1

    # 目标月最后一天
    if month == 12:
        next_month_first = datetime(year + 1, 1, 1, dt.hour, dt.minute, dt.second)
    else:
        next_month_first = datetime(year, month + 1, 1, dt.hour, dt.minute, dt.second)
    last_day = (next_month_first - timedelta(days=1)).day

    day = min(dt.day, last_day)
    return datetime(year, month, day, dt.hour, dt.minute, dt.second)

