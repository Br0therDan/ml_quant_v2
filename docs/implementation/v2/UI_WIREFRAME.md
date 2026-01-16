# Quant Lab V2 UI 설계서 (Draft)

- 문서 목적: V2 Streamlit UI를 **연구실(Workbench)** 형태로 일관되게 재구성하기 위한 UX/UI 기준(SSOT-lite)
- 대상: Quant Lab V2 (Streamlit + Plotly)
- 작성일: 2026-01-15
- 상태: Draft v0.1

---

## 1. UX 철학 및 원칙

### 1.1 네비게이션 원칙
- **사이드바는 “앱(페이지) 네비게이션 전용”**으로만 사용한다.
- 페이지별 컨트롤(필터/선택)은 **페이지 내부 좌측 패널**에 배치한다.
- 사이드바에 컨트롤 위젯을 넣지 않는다.

### 1.2 스크롤 정책
- 전체 화면 스크롤(브라우저 스크롤)은 최소화한다.
- **컨텐츠가 길어지는 경우 “우측 결과 컨테이너 내부 스크롤”을 우선**한다.
- 단, Streamlit의 구조적 한계를 고려하여 다음 우선순위를 적용한다.

**우선순위**
1) (권장) 레이아웃을 압축하여 “스크롤이 거의 필요 없는 화면”을 만든다.  
2) (차선) 결과 영역을 **탭(Tabs)** 으로 나눠서 화면 높이를 제한한다.  
3) (최후) 최소 CSS(단일 파일, 단일 클래스)로 결과 컨테이너만 스크롤 처리한다.

### 1.3 시각적 일관성
- 페이지마다 레이아웃/컴포넌트 위치가 달라지면 사용자가 학습 비용을 지불한다.
- 모든 페이지는 아래 공통 레이아웃을 따른다.

---

## 2. 공통 레이아웃 스펙

### 2.1 기본 설정
- `st.set_page_config(layout="wide", page_title="Quant Lab V2")`
- **Columns 기반 2-panel** 레이아웃을 표준으로 사용한다.

### 2.2 2-Panel 레이아웃 (표준)
- 좌측: **Controls Panel** (25~30%)
- 우측: **Results Panel** (70~75%)

권장 비율:
- `st.columns([0.28, 0.72], gap="large")`

### 2.3 패널 컨테이너 카드 스타일
- 패널 경계(border)는 시각적 안정감을 주며, 내부 스크롤이 있을 때 특히 중요하다.
- “상하단 높이 정렬”이 UX 품질에 큰 영향을 준다.

**요구사항**
- 좌측/우측 컨테이너의 **border 상하단이 정렬**되어야 한다.
- 좌측 패널이 비어보이는 경우, 하단에 “상태 요약/도움말” 슬롯을 추가하여 높이를 맞춘다.

### 2.4 패널 높이 정렬 전략 (CSS 최소화)
Streamlit은 기본적으로 “컬럼 높이 동기화” 기능이 없다.  
따라서 다음 중 하나를 택한다.

**A안 (CSS 없음 / 권장)**  
- 좌측 패널을 “짧게” 만들지 말고, 하단에 `st.info()` 또는 `st.caption()` 기반의 도움말/상태 블록을 배치하여 시각적 높이를 맞춘다.

**B안 (CSS 최소 10줄 / 차선)**  
- `app/ui/layout.py` 같은 단일 파일에만 CSS를 작성한다.
- `.qlv2-panel` 단일 클래스만 정의하여, 컨테이너에 `min-height`를 적용한다.
- 페이지마다 CSS 복붙 금지.

---

## 3. 페이지 정보구조(IA) 제안

### 3.1 최종 페이지 구성 (권장 Minimal Set)
- **Dashboard (통합 대시보드)**
- **Backtest Analyzer**
- **Market Explorer (Data Explorer 업그레이드)**
- (선택) **Symbol & Data Center**: 심볼 등록/커버리지 관리가 필요할 때만 유지

> Pipeline Status는 독립 페이지로 두지 않고 Dashboard에 흡수한다.

---

## 4. 페이지별 설계

## 4.1 Dashboard (통합 대시보드)

### 목적
- “현재 상태 → 최근 결과 → 문제 → 다음 액션”을 한 화면에서 제공한다.

### 레이아웃
- 상단: System Health Bar
- 중단: Pipeline Step Cards (5개)
- 하단: Recent Backtests + Targets Snapshot

### 핵심 위젯
1) **System Health Bar**
- DuckDB/SQLite 경로(축약 표시)
- 마지막 업데이트 시각
- 경고: DuckDB lock 안내(배치 동시 실행 금지)

2) **Pipeline Step Cards (Ingest/Features/Labels/Recommend/Backtest)**
- last status: success/fail
- ended_at, duration
- fail 시 error snippet 1줄
- “open detail” 링크(선택)

3) **Recent Backtests (Top 10)**
- KPI 핵심 열만: run_id, strategy_id, cagr, sharpe, max_dd, turnover, created_at
- 행 선택 시 Backtest Analyzer로 이동(또는 run_id를 session_state에 저장)

### 와이어프레임 (Reference)
![Dashboard Wireframe](/Users/donghakim/.gemini/antigravity/brain/718e03c2-c837-4086-b6c6-a6c276e64733/uploaded_image_1768485566741.png)

### Acceptance Checklist
- [ ] **System Health Bar**: DuckDB/SQLite 상태(OK/FAIL) 표시 및 마지막 인제스트/백테스트 상대 시간 표시
- [ ] **Pipeline Cards**: Ingest, Features, Labels, Recommend, Backtest 5개 카드 가로 배치
- [ ] **Card Details**: 각 카드에 상태 아이콘, 종료 시간(상대), 소요 시간, 실패 시 에러 스니펫 포함
- [ ] **Recent Backtests**: 상위 10개 결과 표시, 최신/Sharpe/CAGR 정렬 기능, 행 클릭 시 세션 상태 저장
- [ ] **Targets Snapshot**: 최신 날짜 기준 전략별 포지션 수, 승인 비율(프로그레스 스타일), 주요 심볼 표시
- [ ] **Navigation**: 사이드바에 컨트롤 위젯 없이 네비게이션 기능만 유지

### 와이어프레임 (ASCII)
```
+----------------------------------------------------------------------------------+
|  System Health: DuckDB OK | SQLite OK | Last Ingest: 10m | Last Backtest: 2m     |
|  ⚠️ 배치 실행 중 Streamlit 동시 실행 비권장 (DuckDB lock)                           |
+----------------------------------------------------------------------------------+

[ Ingest ✅ ] [ Features ✅ ] [ Labels ✅ ] [ Recommend ❌ ] [ Backtest ✅ ]
  - 10m ago      - 9m ago       - 9m ago       - 8m ago       - 2m ago
  - 1.2s         - 3.1s         - 0.9s         - error: ...    - 2.4s

+-------------------------------------+-------------------------------------------+
| Recent Backtests (Top 10)           | Targets Snapshot (Latest)                 |
| run_id | strategy | cagr | sharpe   | strategy | positions | approved | top     |
| ...                                 | ...                                       |
+-------------------------------------+-------------------------------------------+
```

---

## 4.2 Backtest Analyzer

### 목적
- 단일 run의 성과를 “KPI → 곡선 → 트레이드” 순서로 직관적으로 분석한다.
- 2개 run 비교를 빠르게 수행한다.

### 레이아웃 (2-panel + Tabs)
- 좌측 Controls Panel: run/symbol/date/chart 옵션
- 우측 Results Panel: 탭 3개

**좌측 Controls Panel (고정 느낌)**
- Run 선택: `run_id`
- Strategy 필터(optional)
- Date range
- Symbol 선택 (Price+Markers)
- Chart mode: candlestick/line, log scale, volume overlay
- Marker 옵션: buy/sell on/off, threshold

**우측 Results Panel**
- 탭1: Dashboard
  - KPI cards (CAGR, Sharpe, MDD, Total Return, Vol(ann), Turnover, Cost)
  - Equity curve (Equity 1.0 / CumReturn % toggle)
  - Drawdown curve
- 탭2: Run Detail
  - Price + Trade Markers (hover tooltip)
  - Daily Rebalance Ledger (expander로 접기)
- 탭3: Compare Runs
  - KPI 비교 테이블
  - Equity 비교 차트

### 와이어프레임 (Reference)
![Backtest Analyzer Wireframe](/Users/donghakim/.gemini/antigravity/brain/718e03c2-c837-4086-b6c6-a6c276e64733/uploaded_image_1768486170990.png)

### Acceptance Checklist
- [ ] **2-Panel Layout**: 좌측 Controls 패널(28%), 우측 Results 패널(72%) 구성
- [ ] **Dashboard Tab**: 
    - [ ] 6개 KPI 카드 (CAGR, Sharpe, MDD, Vol, Turnover, Cost) + 툴팁
    - [ ] Equity Curve (Equity 1.0 vs CumReturn % 토글)
    - [ ] Drawdown 차트 (압축된 높이) 및 MDD 시작~종료 기간 텍스트 표시
- [ ] **Run Detail Tab**:
    - [ ] 가격 + 트레이드 마커 (Threshold 적용 신호만)
    - [ ] Hover 정보: 일자, 액션, 종가, 전후 비중, 비중 변화, 비용
    - [ ] Daily Rebalance Ledger (기본 닫힘 Expander)
- [ ] **Compare Tab**: KPI 비교 테이블, 병렬 Equity 차트, 핵심 차이점 3줄 요약
- [ ] **Theme consistency**: 별도의 배경색 없이 Streamlit 기본 다크 테마와 완벽 호환

### Trade Markers (정의)
- daily ledger 기반:
  - `delta_weight[t] = weight[t] - weight[t-1]`
  - delta_weight > 0 → BUY
  - delta_weight < 0 → SELL
- Hover tooltip 필수 필드:
  - date, action, close
  - weight_before, weight_after, delta_weight
  - cost(존재 시)

### Ledger 표기 명칭
- “Trade Ledger” 대신 **Daily Rebalance Ledger** 사용을 권장한다.

---

## 4.3 Market Explorer (Data Explorer 업그레이드)

### 목적
- “가격 행동”과 “파생 데이터(Features/Labels)”를 차트 중심으로 검증한다.
- Raw table은 디버깅용(expander)으로만 제공한다.

### 좌측 Controls
- symbol
- date range
- chart type: candlestick / close line
- log scale toggle
- volume overlay toggle
- overlays:
  - SMA(20/60/200)
  - RSI(14)
  - Bollinger(20,2)

### 우측 Results
- 상단: 가격 차트(큰 1장)
- 하단: 탭
  - Features: 주요 피처 라인/분포(선택)
  - Labels: label 비율/분포(선택)
### 와이어프레임 (Reference)
![Market Explorer Wireframe](/Users/donghakim/.gemini/antigravity/brain/718e03c2-c837-4086-b6c6-a6c276e64733/uploaded_image_1768485826496.png)

### Acceptance Checklist
- [ ] **2-Panel Layout**: 좌측 Controls 패널(28%), 우측 Results 패널(72%) 구성
- [ ] **Quick Presets**: 1M, 3M, 6M, 1Y, MAX 등 원클릭 날짜 필터 제공
- [ ] **Chart Overlays**: SMA(20/60/200), RSI(14), Bollinger Bands(20,2) 토글 지원
- [ ] **Chart Features**: Candlestick/Line 전환, Log Scale, Volume Overlay(서브플롯 또는 오버레이)
- [ ] **Features Tab**: 피처별 시계열 차트 및 분포 히스토그램 시각화
- [ ] **Labels Tab**: 정답지(Label)의 양/음 비율 및 수익률 분포 시각화
- [ ] **Performance**: `st.cache_data`를 활용한 쾌적한 데이터 로딩

### 와이어프레임
```
+---------------------------+-----------------------------------------------------------+
| Controls                  | Price Chart (Candlestick/Line)                           |
| - symbol                  | + Overlays (SMA/RSI/BB)                                   |
| - date range              |-----------------------------------------------------------|
| - overlays                | [Features] [Labels]                                       |
+---------------------------+-----------------------------------------------------------+
| (expander) raw tables     | (optional charts / distribution)                          |
+---------------------------+-----------------------------------------------------------+
```

---

## 4.4 Symbol & Data Center (선택)

### 목적
- 심볼 카탈로그/커버리지(일/주/월 데이터 존재)를 빠르게 확인한다.
- 필요 시 심볼 등록을 UI에서 보조한다.

### 레이아웃 (이미지 스타일 유지 권장)
- 좌측: Search / Quick add
- 우측: Catalog & Coverage (tab: stocks/crypto/forex)

### 기능
- 목록 필터(search)
- coverage 표시(daily/weekly/monthly 체크)
- (선택) “선택 심볼 → CLI 명령 복사” 제공

---

## 5. 국제화(i18n) / 카피라이팅
- 기본 언어: 한국어(KO)
- 전문 용어: 한국어(원어) 병기 가능
  - 예: “샤프비율(Sharpe)”, “최대낙폭(Max Drawdown)”

---

## 6. 성능 규칙
- 모든 DuckDB/SQLite 조회는 `st.cache_data` 적용
- 위젯 변경으로 전체 테이블 재스캔 방지:
  - symbol/date 기준으로 캐시 키 분리
- 대용량 테이블은 “요약 먼저, 상세는 expander/탭” 제공

---

## 7. Definition of Done (DoD)
- Dashboard에서 파이프라인 단계별 상태가 “요약 신호”로 보인다.
- Backtest Analyzer에서 run 분석 흐름이 10초 내 이해된다.
- Price + Trade Markers hover가 충분히 상세하다.
- 전체 페이지 스크롤이 과도하지 않다(탭/압축 레이아웃으로 해결).
- CSS는 (필요 시) 단일 파일/단일 클래스만 허용한다.

---

## 8. 추후 확장 (V3)
- Paper/Live trading은 V3에서 구현(본 UI에서는 placeholder 유지)
- Batch 스케줄러/알림은 V3에서 고려

