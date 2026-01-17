
from sqlmodel import Session, select

from quant.config import settings
from quant.models.meta import Symbol

from ..data_curator.provider import AlphaVantageProvider


class SymbolRepo:
    def __init__(
        self, session: Session, provider: AlphaVantageProvider | None = None
    ):
        self.session = session
        self.provider = provider or AlphaVantageProvider(
            api_key=settings.alpha_vantage_api_key
        )

    def register_symbol(self, symbol_name: str) -> Symbol:
        """
        AlphaVantageProvider를 통해 심볼 정보를 조회하고 SQLite 메타 DB에 등록합니다.
        """
        # 0. 이미 존재하는지 확인 (IntegrityError 방지)
        existing = self.get_symbol(symbol_name)
        if existing:
            return existing

        # 1. Provider를 통해 검색/조회
        search_df = self.provider.search_symbols(symbol_name)

        if search_df.empty:
            # 검색 결과가 없으면 최소 정보로 생성
            new_symbol = Symbol(symbol=symbol_name, name=symbol_name)
        else:
            # 첫 번째 검색 결과 사용
            info = search_df.iloc[0]
            new_symbol = Symbol(
                symbol=info["symbol"],
                name=info.get("name"),
                currency=info.get("currency", "USD"),
                # is_active, priority 등은 기본값 유지
            )

        # 2. SQLite에 저장
        self.session.add(new_symbol)
        self.session.commit()
        self.session.refresh(new_symbol)
        return new_symbol

    def list_active_symbols(self) -> list[Symbol]:
        statement = select(Symbol).where(Symbol.is_active)
        return self.session.exec(statement).all()

    def get_symbol(self, symbol_name: str) -> Symbol | None:
        return self.session.get(Symbol, symbol_name)
