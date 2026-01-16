# YAML_SCHEMA.md (V2)
- Version: v2.0.0
- Created: 2026-01-15
- Last Updated: 2026-01-16

> 전략 SSOT는 YAML이며, YAML은 **조립(Assembly) 설정 파일**로만 사용한다.  
> YAML에 로직/수식/조건식을 넣어 DSL화하는 것을 금지한다.

---

## 1. Minimal Schema

### 1.1 Root Fields (Required)
- `strategy_id` (string)
- `version` (string)
- `universe` (object)
- `rebalance` (object)
- `portfolio` (object)
- `supervisor` (object)

### 1.2 Root Fields (Required: One-of)
- `signal` (object) **또는** `recommender` (object)
  - V2 baseline: `signal`
  - V2 ML POC(plugin): `recommender`

### 1.3 Root Fields (Recommended)
- `execution` (object)
- `backtest` (object)

---

## 2. Field Definitions (V2)

### 2.1 universe
- 목적: 종목 풀 선택
- 권장 필드:
  - `type`: `symbols`
  - `symbols`: list[str] (type=symbols일 때)
  - `filters`: optional (추후 확장)

### 2.2 signal
- 목적: 신호 원천 선택(룰/팩터/모델)
- 권장 필드:
  - `type`: `factor_rank` | `model_score`
  - `inputs`: feature/prediction 참조 정보

### 2.3 rebalance
- 목적: 리밸런싱 주기/룰
- 권장 필드:
  - `frequency`: `daily` | `weekly`
  - `asof_policy`: `close`

### 2.4 portfolio
- 목적: Top-K 및 weight 결정
- 권장 필드:
  - `top_k`: int
  - `weighting`: `equal` | `score_weighted`

### 2.5 supervisor (Lightweight R1~R5)
- 권장 필드:
  - `gross_exposure_cap`
  - `max_weight_per_symbol`
  - `max_positions`
  - `turnover_cap`
  - `score_floor` (optional)

### 2.6 execution
- 목적: 체결 가정
- 권장 필드:
  - `price`: `close`

### 2.7 backtest
- 목적: 백테스트 설정
- 권장 필드:
  - `from`
  - `to`
  - `fee_bps`
  - `slippage_bps`

---

## 3. Minimal Example (Reference)

```yaml
strategy_id: "demo_momentum_v1"
version: "1.0.0"

universe:
  type: "symbols"
  symbols: ["AAPL", "MSFT", "NVDA"]

signal:
  type: "factor_rank"
  inputs:
    feature_version: "v1"
    feature_name: "ret_20d"

rebalance:
  frequency: "weekly"
  asof_policy: "close"

portfolio:
  top_k: 5
  weighting: "equal"

supervisor:
  gross_exposure_cap: 1.0
  max_weight_per_symbol: 0.15
  max_positions: 10
  turnover_cap: 0.30

execution:
  price: "close"

backtest:
  from: "2024-01-01"
  to: "2025-12-31"
  fee_bps: 2
  slippage_bps: 10
```

> 위 예시는 “형태 참고” 목적이며, V2에서는 본 스키마를 벗어나지 않는다.
