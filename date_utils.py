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


def parse_datetime_loose(value: str) -> datetime:
    """
    尽量宽松地解析时间字符串（用于管理后台手动录入）。
    支持：
    - ISO: 2026-01-07T12:00:00 / 2026-01-07T12:00:00Z / 带时区偏移
    - 空格分隔: 2026-01-07 12:00:00
    - 斜杠: 2026/1/7 12:00:00
    """
    raw = (value or "").strip()
    if not raw:
        raise ValueError("empty datetime")

    s = raw.replace("Z", "+00:00").replace("/", "-")
    if " " in s and "T" not in s:
        s = s.replace(" ", "T", 1)

    dt = datetime.fromisoformat(s)
    if dt.tzinfo is not None:
        # 统一转换为本地时间的 naive datetime，避免 Z/+00:00 被当成本地时间使用而产生偏移
        local_tz = datetime.now().astimezone().tzinfo
        dt = dt.astimezone(local_tz).replace(tzinfo=None)
    return dt
