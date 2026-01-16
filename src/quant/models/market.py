from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel, UniqueConstraint


class CompanyOverview(SQLModel, table=True):
    __tablename__ = "company_overviews"
    __table_args__ = {"extend_existing": True}

    symbol: str = Field(primary_key=True)
    asset_type: Optional[str] = Field(default=None)
    name: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)
    cik: Optional[str] = Field(default=None)
    exchange: Optional[str] = Field(default=None)
    currency: Optional[str] = Field(default=None)
    country: Optional[str] = Field(default=None)
    sector: Optional[str] = Field(default=None)
    industry: Optional[str] = Field(default=None)
    address: Optional[str] = Field(default=None)
    official_site: Optional[str] = Field(default=None)
    fiscal_year_end: Optional[str] = Field(default=None)
    latest_quarter: Optional[datetime] = Field(default=None)
    market_cap: Optional[int] = Field(default=None)
    ebitda: Optional[int] = Field(default=None)
    pe_ratio: Optional[float] = Field(default=None)
    peg_ratio: Optional[float] = Field(default=None)
    book_value: Optional[float] = Field(default=None)
    dividend_per_share: Optional[float] = Field(default=None)
    dividend_yield: Optional[float] = Field(default=None)
    eps: Optional[float] = Field(default=None)
    revenue_per_share_ttm: Optional[float] = Field(default=None)
    profit_margin: Optional[float] = Field(default=None)
    operating_margin_ttm: Optional[float] = Field(default=None)
    return_on_assets_ttm: Optional[float] = Field(default=None)
    return_on_equity_ttm: Optional[float] = Field(default=None)
    revenue_ttm: Optional[int] = Field(default=None)
    gross_profit_ttm: Optional[int] = Field(default=None)
    diluted_eps_ttm: Optional[float] = Field(default=None)
    quarterly_earnings_growth_yoy: Optional[float] = Field(default=None)
    quarterly_revenue_growth_yoy: Optional[float] = Field(default=None)
    analyst_target_price: Optional[float] = Field(default=None)
    analyst_rating_strong_buy: Optional[int] = Field(default=None)
    analyst_rating_buy: Optional[int] = Field(default=None)
    analyst_rating_hold: Optional[int] = Field(default=None)
    analyst_rating_sell: Optional[int] = Field(default=None)
    analyst_rating_strong_sell: Optional[int] = Field(default=None)
    trailing_pe: Optional[float] = Field(default=None)
    forward_pe: Optional[float] = Field(default=None)
    price_to_sales_ratio_ttm: Optional[float] = Field(default=None)
    price_to_book_ratio: Optional[float] = Field(default=None)
    ev_to_revenue: Optional[float] = Field(default=None)
    ev_to_ebitda: Optional[float] = Field(default=None)
    beta: Optional[float] = Field(default=None)
    high_52week: Optional[float] = Field(default=None)
    low_52week: Optional[float] = Field(default=None)
    ma_50day: Optional[float] = Field(default=None)
    ma_200day: Optional[float] = Field(default=None)
    shares_outstanding: Optional[int] = Field(default=None)
    shares_float: Optional[int] = Field(default=None)
    percent_insiders: Optional[float] = Field(default=None)
    percent_institutions: Optional[float] = Field(default=None)
    dividend_date: Optional[datetime] = Field(default=None)
    ex_dividend_date: Optional[datetime] = Field(default=None)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class EconomicIndicator(SQLModel, table=True):
    __tablename__ = "economic_indicators"
    __table_args__ = (
        UniqueConstraint("name", "date", name="uq_econ_name_date"),
        {"extend_existing": True},
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    title: Optional[str] = Field(default=None)
    date: datetime
    value: float
    unit: Optional[str] = Field(default=None)
    interval: Optional[str] = Field(default=None)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class NewsArticle(SQLModel, table=True):
    __tablename__ = "news_articles"
    __table_args__ = {"extend_existing": True}

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    url: str = Field(unique=True)
    time_published: datetime = Field(index=True)
    summary: Optional[str] = None
    source: Optional[str] = None
    category_within_source: Optional[str] = None
    source_domain: Optional[str] = None
    overall_sentiment_score: Optional[float] = None
    overall_sentiment_label: Optional[str] = None
    ticker_sentiment: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
