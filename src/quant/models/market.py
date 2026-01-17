from datetime import datetime

from sqlmodel import Field, SQLModel, UniqueConstraint


class CompanyOverview(SQLModel, table=True):
    __tablename__ = "company_overviews"
    __table_args__ = {"extend_existing": True}

    symbol: str = Field(primary_key=True)
    asset_type: str | None = Field(default=None)
    name: str | None = Field(default=None)
    description: str | None = Field(default=None)
    cik: str | None = Field(default=None)
    exchange: str | None = Field(default=None)
    currency: str | None = Field(default=None)
    country: str | None = Field(default=None)
    sector: str | None = Field(default=None)
    industry: str | None = Field(default=None)
    address: str | None = Field(default=None)
    official_site: str | None = Field(default=None)
    fiscal_year_end: str | None = Field(default=None)
    latest_quarter: datetime | None = Field(default=None)
    market_cap: int | None = Field(default=None)
    ebitda: int | None = Field(default=None)
    pe_ratio: float | None = Field(default=None)
    peg_ratio: float | None = Field(default=None)
    book_value: float | None = Field(default=None)
    dividend_per_share: float | None = Field(default=None)
    dividend_yield: float | None = Field(default=None)
    eps: float | None = Field(default=None)
    revenue_per_share_ttm: float | None = Field(default=None)
    profit_margin: float | None = Field(default=None)
    operating_margin_ttm: float | None = Field(default=None)
    return_on_assets_ttm: float | None = Field(default=None)
    return_on_equity_ttm: float | None = Field(default=None)
    revenue_ttm: int | None = Field(default=None)
    gross_profit_ttm: int | None = Field(default=None)
    diluted_eps_ttm: float | None = Field(default=None)
    quarterly_earnings_growth_yoy: float | None = Field(default=None)
    quarterly_revenue_growth_yoy: float | None = Field(default=None)
    analyst_target_price: float | None = Field(default=None)
    analyst_rating_strong_buy: int | None = Field(default=None)
    analyst_rating_buy: int | None = Field(default=None)
    analyst_rating_hold: int | None = Field(default=None)
    analyst_rating_sell: int | None = Field(default=None)
    analyst_rating_strong_sell: int | None = Field(default=None)
    trailing_pe: float | None = Field(default=None)
    forward_pe: float | None = Field(default=None)
    price_to_sales_ratio_ttm: float | None = Field(default=None)
    price_to_book_ratio: float | None = Field(default=None)
    ev_to_revenue: float | None = Field(default=None)
    ev_to_ebitda: float | None = Field(default=None)
    beta: float | None = Field(default=None)
    high_52week: float | None = Field(default=None)
    low_52week: float | None = Field(default=None)
    ma_50day: float | None = Field(default=None)
    ma_200day: float | None = Field(default=None)
    shares_outstanding: int | None = Field(default=None)
    shares_float: int | None = Field(default=None)
    percent_insiders: float | None = Field(default=None)
    percent_institutions: float | None = Field(default=None)
    dividend_date: datetime | None = Field(default=None)
    ex_dividend_date: datetime | None = Field(default=None)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class EconomicIndicator(SQLModel, table=True):
    __tablename__ = "economic_indicators"
    __table_args__ = (
        UniqueConstraint("name", "date", name="uq_econ_name_date"),
        {"extend_existing": True},
    )

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    title: str | None = Field(default=None)
    date: datetime
    value: float
    unit: str | None = Field(default=None)
    interval: str | None = Field(default=None)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class NewsArticle(SQLModel, table=True):
    __tablename__ = "news_articles"
    __table_args__ = {"extend_existing": True}

    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    url: str = Field(unique=True)
    time_published: datetime = Field(index=True)
    summary: str | None = None
    source: str | None = None
    category_within_source: str | None = None
    source_domain: str | None = None
    overall_sentiment_score: float | None = None
    overall_sentiment_label: str | None = None
    ticker_sentiment: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
