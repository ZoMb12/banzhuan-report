from datetime import timedelta
from typing import List

from data.models import ItemSnapshot, PriceRecord, WindowResult


def is_price_stable(price_history: List[PriceRecord], threshold: float = 0.05) -> bool:
    if not price_history:
        return False
    prices = [r.price for r in price_history]
    avg_price = sum(prices) / len(prices)
    if avg_price == 0:
        return False
    if len(prices) < 2:
        return True
    volatility = (max(prices) - min(prices)) / avg_price
    return volatility <= threshold


def apply_initial_filters(items: List[ItemSnapshot],
                          min_price: float = 20.0,
                          min_volume: int = 100) -> List[ItemSnapshot]:
    result = []
    for item in items:
        if item.volume < min_volume:
            continue
        if item.buff_price <= min_price:
            continue
        result.append(item)
    return result


def find_stable_windows(
    item_id: str,
    item_name: str,
    price_history: List[PriceRecord],
    window_days: int = 24,
    threshold: float = 0.05,
    min_price: float = 20.0,
    min_records: int = 5,
) -> List[WindowResult]:
    """Scan price history with a sliding window, return all qualifying windows."""
    if not price_history:
        return []

    sorted_records = sorted(price_history, key=lambda r: r.date)
    qualifying_windows: List[WindowResult] = []
    seen_starts = set()

    for i, record in enumerate(sorted_records):
        window_start = record.date
        if window_start in seen_starts:
            continue
        seen_starts.add(window_start)

        window_end = window_start + timedelta(days=window_days)

        window_records = []
        for j in range(i, len(sorted_records)):
            if sorted_records[j].date <= window_end:
                window_records.append(sorted_records[j])
            else:
                break

        if len(window_records) < min_records:
            continue

        prices = [r.price for r in window_records]
        if min(prices) <= min_price:
            continue

        avg_price = sum(prices) / len(prices)
        if avg_price == 0:
            continue

        volatility = (max(prices) - min(prices)) / avg_price
        if volatility <= threshold:
            qualifying_windows.append(WindowResult(
                item_id=item_id,
                item_name=item_name,
                window_start=window_start,
                window_end=window_end,
                buff_records=window_records,
                buff_avg_price=avg_price,
                buff_min_price=min(prices),
                buff_max_price=max(prices),
                volatility=volatility,
            ))

    return qualifying_windows
