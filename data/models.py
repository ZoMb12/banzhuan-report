from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional


@dataclass
class PriceRecord:
    date: date
    price: float
    volume: int = 0


@dataclass
class ItemSnapshot:
    item_id: str
    name: str
    buff_price: float
    volume: int
    turnover: float = field(init=False)
    price_history: List[PriceRecord] = field(default_factory=list)
    steam_url: Optional[str] = field(default=None)
    steam_price: Optional[float] = field(default=None)
    steam_sold_count: int = 0
    steam_price_history: List[PriceRecord] = field(default_factory=list)

    def __post_init__(self):
        self.turnover = self.buff_price * self.volume


@dataclass
class WindowResult:
    """A qualifying 24-day window where an item passed all filters."""
    item_id: str
    item_name: str
    window_start: date
    window_end: date
    buff_records: List[PriceRecord] = field(default_factory=list)
    buff_avg_price: float = 0.0
    buff_min_price: float = 0.0
    buff_max_price: float = 0.0
    volatility: float = 0.0

    # Steam data (populated in Step 3)
    steam_records: List[PriceRecord] = field(default_factory=list)
    steam_avg_price_usd: Optional[float] = None

    # Step 4 results
    steam_avg_price_cny: Optional[float] = None
    avg_diff: Optional[float] = None
    avg_profit_rate: Optional[float] = None
    is_target: bool = False
    date_pairs: list = field(default_factory=list)  # [{buff_date, buff_price, steam_date, steam_price_usd, steam_price_cny, diff}, ...]
