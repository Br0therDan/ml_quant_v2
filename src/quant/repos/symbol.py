from typing import List, Optional
from sqlmodel import select, Session
from quant.models import Symbol
from quant.services.market_data import MarketDataService
from quant.config import settings


class SymbolRepo:
    def __init__(self, session: Session, service: Optional[MarketDataService] = None):
        self.session = session
        self.service = service or MarketDataService()

    def register_symbol(self, symbol_name: str) -> Symbol:
        """
        market_data client를 통해 심볼 정보를 조회하고 SQLite 메타 DB에 등록합니다.
        """
        # 0. 이미 존재하는지 확인 (IntegrityError 방지)
        existing = self.get_symbol(symbol_name)
        if existing:
            return existing

        # 1. MarketDataService를 통해 검색/조회 (결합도 낮춤)
        search_df = self.service.search_symbols(symbol_name)

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

    def list_active_symbols(self) -> List[Symbol]:
        statement = select(Symbol).where(Symbol.is_active == True)
        return self.session.exec(statement).all()

    def get_symbol(self, symbol_name: str) -> Optional[Symbol]:
        return self.session.get(Symbol, symbol_name)
