import os
from datetime import datetime

from sqlmodel import Session, SQLModel, col, create_engine, select

from quant.config import settings
from quant.models import CompanyOverview, EconomicIndicator, NewsArticle, Symbol

# Use paths from quant settings
DB_PATH = settings.quant_sqlite_path


class MetaStore:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.engine = create_engine(f"sqlite:///{self.db_path}")
        self._init_db()

    def _init_db(self):
        # Always try to create tables first
        try:
            SQLModel.metadata.create_all(self.engine)
        except Exception as e:
            if "already exists" in str(e).lower():
                pass
            else:
                raise e

        try:
            # Safer empty check
            with self.get_session() as session:
                from sqlalchemy import inspect

                inspector = inspect(self.engine)
                if "symbols" in inspector.get_table_names():
                    count = session.exec(select(Symbol).limit(1)).first()
                    if not count:
                        self.seed_from_csv()
        except Exception:
            pass

    def get_session(self) -> Session:
        return Session(self.engine)

    def save_symbol(self, symbol_data: dict):
        with self.get_session() as session:
            symbol = Symbol(**symbol_data)
            session.merge(symbol)
            session.commit()

    def seed_from_csv(self):
        """Seed initial data from static CSVs (Crypto, Forex)."""
        import csv

        # Static CSVs are now assumed to be in the market_data/static directory
        # We need to find its path relative to this file or project root
        project_root = Path(__file__).parent.parent.parent.parent
        static_dir = project_root / "market_data" / "static"

        # 1. Crypto
        crypto_path = os.path.join(static_dir, "crypto_symbols.csv")
        if os.path.exists(crypto_path):
            with open(crypto_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                with self.get_session() as session:
                    for row in reader:
                        s = row["from_currency"]
                        # Upsert with compound PK
                        curr = row["to_currency"]
                        stmt = select(Symbol).where(
                            Symbol.symbol == s,
                            Symbol.type == "CRYPTO",
                            Symbol.currency == curr,
                        )
                        obj = session.exec(stmt).first()
                        if not obj:
                            obj = Symbol(
                                symbol=s,
                                name=s,
                                type="CRYPTO",
                                currency=curr,
                            )
                            session.add(obj)
                        session.commit()

        # 2. Forex
        forex_path = os.path.join(static_dir, "forex_currencies.csv")
        if os.path.exists(forex_path):
            with open(forex_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                with self.get_session() as session:
                    for row in reader:
                        s = row["currency code"]
                        stmt = select(Symbol).where(
                            Symbol.symbol == s,
                            Symbol.type == "FOREX",
                            Symbol.currency == s,
                        )
                        obj = session.exec(stmt).first()
                        if not obj:
                            obj = Symbol(
                                symbol=s,
                                name=row["currency name"],
                                type="FOREX",
                                currency=s,
                            )
                            session.add(obj)
                    session.commit()

    def save_company_overview(self, overview: CompanyOverview):
        with self.get_session() as session:
            # Upsert
            existing = session.get(CompanyOverview, overview.symbol)
            if existing:
                for k, v in overview.model_dump(exclude_unset=True).items():
                    setattr(existing, k, v)
                existing.updated_at = datetime.utcnow()
                session.add(existing)
            else:
                session.add(overview)

            # Also upsert to Symbol table (Master Index)
            a_type = overview.asset_type or "Equity"
            curr = overview.currency or "USD"
            stmt = select(Symbol).where(
                Symbol.symbol == overview.symbol,
                Symbol.type == a_type,
                Symbol.currency == curr,
            )
            sym = session.exec(stmt).first()
            if sym:
                sym.name = overview.name
                sym.currency = curr
                sym.updated_at = datetime.utcnow()
                session.add(sym)
            else:
                session.add(
                    Symbol(
                        symbol=overview.symbol,
                        name=overview.name,
                        type=a_type,
                        currency=curr,
                    )
                )

            session.commit()

    def get_economic_indicator(self, name: str) -> list[EconomicIndicator]:
        with self.get_session() as session:
            stmt = (
                select(EconomicIndicator)
                .where(EconomicIndicator.name == name)
                .order_by(EconomicIndicator.date)
            )
            return list(session.exec(stmt).all())

    def save_economic_indicators(self, indicators: list[EconomicIndicator]):
        if not indicators:
            return
        with self.get_session() as session:
            for ind in indicators:
                # We have a composite unique constraint (name, date)
                # But SQLModel/SQLAlchemy doesn't support 'upsert' elegantly across all DBs without dialect specific code.
                # For SQLite, we can check existence or use simpler "ignore if exists" logic if mass inserting.
                # Or checking one by one if volume is low. Econ data is low volume.

                # Check exist
                stmt = select(EconomicIndicator).where(
                    EconomicIndicator.name == ind.name,
                    EconomicIndicator.date == ind.date,
                )
                existing = session.exec(stmt).first()
                if existing:
                    existing.value = ind.value
                    existing.updated_at = datetime.utcnow()
                    session.add(existing)
                else:
                    session.add(ind)
            session.commit()

    def save_news(self, articles: list[NewsArticle]):
        if not articles:
            return
        with self.get_session() as session:
            for art in articles:
                # Upsert by URL
                existing = session.exec(
                    select(NewsArticle).where(NewsArticle.url == art.url)
                ).first()
                if not existing:
                    session.add(art)
            session.commit()

    def get_news(self, ticker: str = None, limit: int = 50) -> list[NewsArticle]:
        with self.get_session() as session:
            stmt = (
                select(NewsArticle)
                .order_by(col(NewsArticle.time_published).desc())
                .limit(limit)
            )
            if ticker:
                # Very naive search in ticker_sentiment string field
                stmt = stmt.where(col(NewsArticle.ticker_sentiment).contains(ticker))
            return list(session.exec(stmt).all())
