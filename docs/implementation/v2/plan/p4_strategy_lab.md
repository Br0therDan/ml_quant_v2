# V2 Phase P4 Implementation Plan: Strategy Lab + Supervisor + Targets

버전: v1.0.0
작성일: 2026-01-15

## Executive Summary
Phase P4에서는 전략 정의(YAML)를 바탕으로 데이터(Feature Store)를 분석하여 포트폴리오 추천(Targets)을 생성하는 핵심 로직을 구축한다. 이 과정에서 5가지 리스크 관리 규칙(R1~R5)을 적용하는 Supervisor 모듈을 통해 포트폴리오의 안정성을 확보한다.

## Objective
- Strategy YAML 로더 구현 (v2 규격 준수)
- 팩터 기반 랭킹 추천(Targets) 생성 로직 구현 (Baseline)
- Portfolio Supervisor (R1~R5) 구현 및 적용
- `quant recommend` CLI 커맨드 및 Run Registry 연동
- DuckDB `targets` 테이블 적재 및 `approved` 필드 관리

## Progress Dashboard
| Phase | Task | Status | Note |
|---|---|---|---|
| P4.1 | Strategy YAML Loader 구현 | [ ] | Schema validation 포함 |
| P4.2 | 팩터 기반 추천(Targets) 생성 | [ ] | Baseline: Rank-based selection |
| P4.3 | Portfolio Supervisor 구현 | [ ] | R1~R5 규칙 엔진 |
| P4.4 | CLI & Run Registry 연동 | [ ] | recommend 커맨드 |
| P4.5 | 동작 검증 및 Snapshot | [ ] | 최종 검증 |

## Implementation Plan

### 1. Strategy Lab 구현 (`src/quant/strategy_lab/`)
- [ ] `loader.py`: YAML 파일을 읽고 `V2_SYSTEM_SPEC.md`의 스키마를 만족하는지 검사하는 클래스 구현.
- [ ] `recommender.py`: DuckDB에서 피처 데이터를 로드하고 랭킹 기반으로 추천 종목을 선정하는 로직 구현.
    - 입력: `feature_version`, `feature_name`, `asof` 날짜
    - 로직: 해당 날짜의 팩터 값 기준 내림차순 랭킹 → Top-K 선정 → 가중치 부여(Equal Weight 기본)

### 2. Portfolio Supervisor 구현 (`src/quant/portfolio_supervisor/`)
- [ ] `engine.py`: 추천된 종목들에 대해 5가지 규칙 적용.
    - R1: Gross Exposure Cap (비중 합계 제한)
    - R2: Max Position Weight (개별 종목 비중 상한)
    - R3: Max Positions (보유 종목 수 상한)
    - R4: Turnover Cap (교체량 제한 - V2 P4에서는 Placeholder 구조만 마련)
    - R5: Score Floor / Top-K Gate
- [ ] 검증 결과(`approved`, `risk_flags`) 산출 로직.

### 3. CLI 및 Run Registry 연동 (`src/quant/cli.py`)
- [ ] `quant recommend` 커맨드 추가
    - `--strategy <path>`, `--asof YYYY-MM-DD` 인자 지원
    - 실행 전 "DuckDB write 작업 중 Streamlit 동시 실행 권장하지 않음" 경고 출력
    - `RunRegistry.run_start(kind="recommend")` 및 결과 기록

### 4. 문서 업데이트
- [ ] `docs/implementation/v2/RUNBOOK.md`에 Streamlit 종료 관련 운영 규칙 추가.

## Verification Plan
### Automated Tests & 쿼리
- `strategies/example.yaml` 작성 및 `uv run quant recommend` 실행 가능 여부 확인.
- DuckDB 검증 쿼리:
    ```sql
    SELECT * FROM targets 
    WHERE strategy_id='demo_momentum_v1' AND asof=DATE '2025-12-31' 
    ORDER BY approved DESC, score DESC LIMIT 50;
    ```
- SQLite `runs` 확인: `kind='recommend'`, `status='success'`.

### Manual Verification
- YAML 파일의 필수 필드 누락 시 에러 처리 및 `run_fail` 로그 확인.
- `approved=false`인 경우 `risk_flags`가 올바르게 기록되었는지 확인.
