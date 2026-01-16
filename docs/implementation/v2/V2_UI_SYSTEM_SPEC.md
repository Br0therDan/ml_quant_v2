# Quant Lab V2 — UI 추가 설계서 (UI System Spec)

- 목적: V2에서 **CLI 기능을 GUI로 흡수**하기 위한 UI 정보구조(IA) + 페이지별 스펙을 정의한다.
- 범위: Streamlit UI (navigation-only sidebar, page-internal control panels)
- 작성일: 2026-01-15
- 버전: v0.1 (Draft)

---

## 0. 핵심 결론

현재 UI(대시보드/마켓/타겟/백테스트)만으로는 CLI 기능을 모두 GUI로 가져오기에 부족하다.  
V2 UI는 아래 3개 영역을 분리해 “연구실(Workbench)” 워크플로우를 완성해야 한다.

1) **Control Plane**: 실행/오케스트레이션 + 로그 + 실패 대응  
2) **Research Plane**: 데이터/피처/추천/백테스트 분석  
3) **Authoring Plane**: 전략(YAML) 구성/검증/평가

---

## 1. UX 원칙 (V2 표준)

### 1.1 사이드바
- 사이드바는 **네비게이션 전용**
- 컨트롤(필터/옵션/버튼)은 **페이지 내부 좌측 패널**에 배치

### 1.2 레이아웃
- 모든 페이지는 공통적으로 **2-Panel Layout**을 사용한다.

권장 비율:
- Controls Panel: 25~30%
- Results Panel: 70~75%

예시:
- `st.columns([0.28, 0.72], gap="large")`

### 1.3 스크롤 정책
- 전체 스크롤(브라우저)은 최소화
- 상세 테이블/긴 로그는 **컨테이너 내부 스크롤** 또는 **expander** 사용
- 결과 영역은 **Tabs**로 분리하여 높이를 제한

### 1.4 “실험실 UX” 기본 흐름
- (1) 설정 → (2) 실행 → (3) 로그 확인 → (4) 결과 분석 → (5) 재실행
- UI가 반드시 “실행(Trigger)”을 제공해야 한다.

---

## 2. 페이지 구성 (Information Architecture)

### 2.1 권장 Minimal Set (V2 필수 6개)
1) **Dashboard** (통합 요약)
2) **Run Center** (오케스트레이션/실행기)  ← 신규
3) **Data Center** (심볼/인게스트/시장 데이터)
4) **Feature Lab** (피처 엔지니어링/분석)  ← 신규
5) **Strategy Lab** (전략 YAML 검증/평가) ← 신규
6) **Backtest Lab** (실행 + 분석)

### 2.2 확장(선택) 페이지 (V2 후반)
- **Targets & Supervisor** (추천 결과 승인/변화 추적)
- **Runs & Artifacts Explorer** (실행 이력/산출물 탐색)

---

## 3. 실행 기능 표준화 (UI ↔ CLI Mapping)

### 3.1 UI 실행 버튼 표준
모든 실행은 “Run 요청”으로 취급하며, UI는 최소 다음 버튼을 제공한다.

- Run Ingest
- Run Features
- Run Labels
- Run Recommend
- Run Backtest
- Run Pipeline (All)
- Dry Run (Plan only)

### 3.2 최소 구현 방식 (V2 권장)
- UI 버튼 클릭 → **CLI subprocess 실행**
- 실행 로그는 파일로 저장: `artifacts/runs/<run_id>/pipeline.log`
- UI는 log 파일을 주기적으로 읽어 Tail 형태로 표시

> V3에서 Worker 방식(daemon)으로 확장 가능.

### 3.3 실행 중 UX 요구사항
- 실행 시작 시 반드시:
  - `run_id` 표시
  - status: running/success/fail
  - 로그 창(컨테이너)
- 실행 종료 시:
  - 실패면 error_text 요약
  - 성공이면 “분석 페이지로 이동” CTA 제공(Backtest Lab 등)

### 3.4 동시 실행 제어 (DuckDB Lock 위험)
- 기본 정책: **단일 실행만 허용**
- 실행 중에는:
  - 모든 실행 버튼 disable
  - (옵션) heavy query(대형 테이블 스캔) 제한
- 경고 배너:
  - “배치 실행 중 UI 동시 조회는 DuckDB lock 위험이 있음”

---

## 4. 페이지별 상세 스펙

---

# 4.1 Dashboard (통합)

### 목적
- 현재 상태 → 최근 결과 → 문제 → 다음 액션을 한 화면에서 제공

### Controls Panel (좌)
- Strategy YAML 선택(선택)
- Date Range (from/to)
- Symbols (optional)
- [Run Pipeline] [Dry Run]
- (옵션) stages 멀티 선택 + [Run Selected]

### Results Panel (우)
1) System Health Bar
- DuckDB OK/FAIL, SQLite OK/FAIL
- Last Ingest / Last Backtest timestamp

2) Pipeline Step Cards (5개)
- ingest/features/labels/recommend/backtest
- status, ended_at, duration, error snippet

3) Recent Backtests (Top 10)
- run_id, strategy, cagr, sharpe, mdd, turnover, created_at
- run_id 클릭 시 Backtest Lab로 이동

4) Latest Targets Snapshot (선택)
- strategy, positions, approved ratio, top symbols

### Wireframe
```
+--------------------------------------------------------------------------------+
| System Health: DuckDB OK | SQLite OK | Last Ingest: 10m | Last Backtest: 2m    |
+--------------------------------------------------------------------------------+
[ Ingest ✅ ] [ Features ✅ ] [ Labels ✅ ] [ Recommend ❌ ] [ Backtest ✅ ]
+-------------------------------+-----------------------------------------------+
| Recent Backtests (Top 10)     | Latest Targets Snapshot                      |
+-------------------------------+-----------------------------------------------+
```

---

# 4.2 Run Center (오케스트레이션/실행기)  ✅ 신규 (핵심)

### 목적
- UI에서 파이프라인/스테이지 실행을 “운영” 수준으로 제공
- 실행 로그 확인 + 실패 원인 파악 + 재실행

### Controls Panel (좌)
- Strategy YAML path
- Date range
- Symbols (optional)
- Stages multi-select (ingest/features/labels/recommend/backtest)
- toggles:
  - fail-fast (default true)
  - dry-run
- Buttons:
  - [Run Pipeline]
  - [Run Selected Stages]
  - [Cancel] (V2에서는 placeholder 가능)

### Results Panel (우)
- Tabs: [Live Log] [Recent Runs] [Failures]
1) Live Log
- current run_id
- status badge
- tail log view (last N lines)
2) Recent Runs
- 최근 30개 runs 필터(kind/status)
3) Failures
- 최근 실패 Top 10 + error_text 요약
- 클릭 시 run_id 상세(log + config_json)

### Wireframe
```
+--------------------------+---------------------------------------------------+
| Controls                 | [Live Log] [Recent Runs] [Failures]               |
| - strategy.yaml          | RUN_ID: ...   STATUS: running                     |
| - from/to                | +-----------------------------------------------+ |
| - symbols                | | tail log lines...                             | |
| - stages multi           | +-----------------------------------------------+ |
| [Run Pipeline] [Dry Run] |                                                   |
+--------------------------+---------------------------------------------------+
```

---

# 4.3 Data Center (Market & Ingest)

### 목적
- 심볼 관리 + OHLCV 품질 검증 + ingest 실행을 한 화면에서 제공

### Controls Panel (좌)
- Symbol select / Search
- Date range preset (1M/3M/6M/1Y/MAX)
- Chart mode: close line / candlestick
- toggles: log scale, volume overlay
- Buttons:
  - [Register Symbol] (optional)
  - [Run Ingest]  ← selected symbol(s)
  - [Run Features] (optional, 빠른 재생성)
- Expander: raw table 보기(선택)

### Results Panel (우)
- Price chart (큰 1장)
- Tabs:
  - OHLCV Summary (count, missing, dup)
  - Quality Gate (invalid price, gap stats)
  - Coverage (daily/weekly/monthly availability)

---

# 4.4 Feature Lab (피처 분석/엔지니어링) ✅ 신규

### 목적
- “피처 생성 결과”를 분석하고 노이즈/누수/결측을 빠르게 탐지한다.
- 피처 그룹(프리셋) 기반으로 시각화/요약을 제공한다.

### Controls Panel (좌)
- Universe scope:
  - symbol(single) / universe(multi)
- Date range
- Feature preset:
  - Trend (SMA/EMA/ROC)
  - Volatility (ATR/STD)
  - Momentum (RSI/MACD)
  - (Custom) select columns
- View mode:
  - Timeseries
  - Distribution
  - Correlation
- Buttons:
  - [Run Features] (해당 범위/심볼)
  - [Export Feature Summary] (artifact)

### Results Panel (우)
- Tabs: [Timeseries] [Distribution] [Correlation] [Missingness]
1) Timeseries: top N feature 라인차트
2) Distribution: feature 히스토그램 + outlier count
3) Correlation: 상관(heatmap 또는 상위 상관쌍 테이블)
4) Missingness: 결측률 Top 리스트 + 기간별 결측(요약)

### 최소 KPI 카드
- #features, missing%, dup_rows, top_corr_pair

---

# 4.5 Strategy Lab (전략 생성/평가/검증) ✅ 신규

### 목적
- YAML 전략을 “작성(최소) + 검증 + 요약 + 평가 실행”까지 제공한다.
- YAML을 DSL로 확장하지 않는다(전략 조립용 설정 파일로 제한).

### Controls Panel (좌)
- Strategy YAML 선택
- (옵션) YAML 텍스트 보기/간단 편집(expander)
- Buttons:
  - [Validate YAML] (YAML_SCHEMA)
  - [Dry Run Plan]
  - [Run Recommend]
  - [Run Backtest]
  - [Run Pipeline]
- Params:
  - date range
  - symbols override(optional)

### Results Panel (우)
- Strategy Summary Card:
  - universe, features preset, label, model, constraints
- Validation result:
  - OK / error list
- Evaluation shortcuts:
  - 최신 backtest 결과 링크
  - 최근 targets 링크

---

# 4.6 Backtest Lab (실행 + 분석)

### 목적
- run 실행 + KPI + 곡선 + 트레이드 마커 분석

### Controls Panel (좌)
- run_id 선택
- strategy 필터(optional)
- date range
- symbol
- chart mode: close line / candlestick
- marker threshold
- Buttons:
  - [Run Backtest]
  - [Compare Selected Runs] (optional)

### Results Panel (우)
- Tabs: [Dashboard] [Trades] [Compare]
- Trades 탭 핵심 요구사항:
  - **Close 라인 차트 위에 BUY/SELL 마커 오버레이**
  - tooltip: ts, price, qty, pnl/pnl%, fees/slippage
- KPI 표기:
  - nan 금지 → “—” 처리

---

## 5. 로그/아티팩트 표준

### 5.1 폴더 규약
- `artifacts/runs/<run_id>/pipeline.log`
- `artifacts/runs/<run_id>/summary.json`
- (선택) `artifacts/runs/<run_id>/charts/*.png`

### 5.2 UI 로그 보기 규칙
- tail log view는 기본 300~500줄
- “Download log” 버튼 제공(선택)

---

## 6. 완료 기준 (DoD)

- UI에서 pipeline/stage 실행이 가능하고, run_id + 로그가 표시된다.
- Feature Lab이 존재하며, features 결과를 시계열/분포/상관으로 최소 분석 가능하다.
- Strategy Lab에서 YAML 검증/요약/평가 실행이 가능하다.
- Backtest Lab에서 close 라인 위 trade marker가 의미 있게 보인다.
- Sidebar는 navigation-only를 유지한다.

---

## 7. 구현 우선순위 (권장)

1) Run Center (오케스트레이션)  
2) Backtest Lab trade marker/토글 수정  
3) Feature Lab MVP  
4) Strategy Lab MVP  
5) Data Center 실행 버튼 강화  
6) Targets & Supervisor (후반)
