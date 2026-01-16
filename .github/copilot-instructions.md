# Copilot Instructions (Quant Lab V2)

> 이 문서는 **Quant Lab V2 코드베이스 작업 시** Copilot / Gemini / 기타 에이전트를 동일한 기준으로 통제하기 위한 지침이다.
> 
> - 파일명: `copilot-instructions.md` (또는 `GEMINI.md`와 동일 내용으로 복제)
> - 언어: **한국어**
> - 목적: **최소 변경 / 재현성 / 계약(contracts) 유지 / UAT 안정화**

---

## 0) 절대 원칙 (Non‑Negotiable)

1. **실행의 실체는 CLI이다**
   - GUI/Streamlit/TUI는 전부 `quant pipeline run`을 호출하는 **프론트엔드**일 뿐이다.
   - 실행 로직을 UI로 옮기지 않는다.

2. **Run Contract를 절대 깨지 않는다**
   - `PLAN_JSON` / (향후) `RUN_JSON` 출력 규약
   - `run_id` 중심 재현성
   - `stages_resolved`, `symbols_resolved` 등 “resolved vs requested” 분리

3. **실행 산출물은 오직 `artifacts/` 아래로만 저장한다 (SSOT)**
   - 허용: `artifacts/runs/<run_id>/...`
   - 금지: `./runs/`, `./models/`, `./strategies/generated/`, 프로젝트 루트에 생성
   - 전략 파생 파일(자동 생성 YAML 등)은 `artifacts/runs/<run_id>/generated/`로 저장

4. **V2는 UAT/실험 플랫폼이다 (Production 시스템 아님)**
   - 목표: 파이프라인 안정성, 재현성, 관제(Run Center), 아티팩트/로그 정리
   - ML은 **baseline 대체가 아니라 plugin POC**로만 추가

---

## 1) 작업 방식 규칙 (Checklist‑First)

- 모든 작업은 아래 순서를 반드시 따른다.

### 1.1 Step 1 — 스캔
- 관련 디렉토리/파일을 `rg`로 먼저 탐색한다.
- 변경 범위를 최소화할 수 있는 위치를 찾는다.

### 1.2 Step 2 — 계약 확인
- 변경이 **Run Contract / artifacts 경로 / stage 순서**에 영향을 주는지 검토한다.
- 영향이 있으면 문서(`docs/`, `run_contract.md`)도 함께 업데이트한다.

### 1.3 Step 3 — 최소 변경 구현
- “리팩토링 욕심” 금지.
- 기능 추가는 플러그인/옵션 형태로만.

### 1.4 Step 4 — 테스트/검증
- 가능한 경우 pytest 추가/수정
- 최소한 `quant pipeline run --dry-run` 케이스를 통과

---

## 2) CLI / Pipeline 규칙

### 2.1 파이프라인 엔트리포인트
- 표준 실행:
  - `quant pipeline run --strategy ... --from ... --to ...`
- dry-run:
  - `quant pipeline run ... --dry-run`

### 2.2 Stage 계약
- V2 pipeline stages는 다음 5개만 공식 지원한다.
  - `ingest`, `features`, `labels`, `recommend`, `backtest`
- stage 확장은 “V3 범위”로 취급하고, V2에서는 신중히 진행한다.

### 2.3 dry-run 계약
- `--dry-run`은 **실행 금지(Write 금지)**
  - DuckDB/SQLite write 금지
  - 외부 API 호출은 원칙적으로 금지
- stdout에는 반드시 1줄의 `PLAN_JSON: {...}`가 포함되어야 한다.
- `artifacts/runs/<run_id>/plan.json`이 생성되어야 한다.

---

## 3) Artifacts/ 경로 표준 (SSOT)

### 3.1 디렉토리 규칙

```
artifacts/
  runs/
    <run_id>/
      plan.json
      run.json                # (향후)
      pipeline.log
      stages/
        ingest/
        features/
        labels/
        recommend/
        backtest/
      outputs/
      reports/
      generated/
```

### 3.2 저장 금지 영역
- `strategies/` 아래에 실행 산출물 생성 금지
- repo root에 로그/모델 생성 금지

---

## 4) Streamlit UI 원칙

### 4.1 Run Center 단일 실행 진입점
- 실행(trigger)은 **2_Run_Center**에서만 가능
- 다른 페이지(Dashboard/Data/Feature/Strategy/Backtest/Targets)는 **read‑only**

### 4.2 Plan → Run 흐름 강제
- `Plan(dry-run)` 결과가 `validation.ok=true`일 때만 Run 버튼 활성화
- UI는 `PLAN_JSON`을 파싱해 구조적으로 보여준다.

### 4.3 UI에서 DB Write 금지
- UI는 오직 “실행 요청”과 “아티팩트/로그 조회”만 담당

---

## 5) ML POC 규칙 (V2 → V3 브릿지)

### 5.1 원칙
- ML은 **추천 엔진(recommend) 내부의 plugin 옵션**으로만 추가
- baseline `factor_rank`를 절대 제거/변경하지 않는다.
- downstream(backtest) 입력 계약(targets)은 그대로 유지한다.

### 5.2 최소 POC 권장
- 모델군: LightGBM / XGBoost / CatBoost (GBDT)
- 문제 설정: 회귀(예: forward_ret_5d)
- Split: 시간축 기준(train/valid/test) — 랜덤 split 금지
- Optuna/Registry/Online learning은 V2에서 금지(또는 후순위)

---

## 6) 문서화 규칙 (필수)

### 6.1 공통 규칙
- 문서는 한국어
- 상단에 버전/작성일/최종수정일 표기
- 장황한 예시는 금지(최소 예시만)

### 6.2 문서 구조 템플릿
문서는 아래 섹션을 유지한다.

1. Executive Summary
2. Objective
3. Progress Dashboard (표)
4. Implementation Plan (체크박스 포함)

### 6.3 문서 저장 경로
- `docs/implementation/v2/plan/`
- `docs/implementation/v2/walkthrough/`

---

## 7) 테스트 규칙

- PR/변경 단위마다 pytest를 최소 1개 이상 보강한다.
- 필수 테스트 케이스:
  - `PLAN_JSON` 존재 및 JSON 파싱
  - `artifacts/runs/<run_id>/plan.json` 생성
  - `--symbols` override 반영
  - `--stages` subset 반영
  - invalid stage 입력 시 실패(exit!=0)

---

## 8) 툴링 규칙

- 패키지관리자: `uv` 
  - 가상환경: `venv` (프로젝트 루트 `.venv/`)
  - 실행: `uv run quant ...`
- 코드 스타일: `black` + `isort` + `ruff`
- 텍스트 검색: `rg`(ripgrep) 사용
- 변경은 “최소/명확” 우선
- 불확실한 라이브러리 사용법은 문서 우선 확인
  - 특히: `duckdb`, `sqlalchemy/sqlmodel`, `typer`, `rich`, `streamlit`

---

## 9) 커뮤니케이션 규칙

- 사용자/리뷰 출력은 한국어
- 모호한 요청도 멈추지 말고 **가정 기반 작업안 + 다음 액션**을 제시
- 데이터 손실/스키마 파괴/대규모 리팩토링은 리스크를 명시

---

## 10) V2 ↔ V3 범위 선언 (README에도 동일하게 반영)

- **V2**: UAT/실험 파이프라인
  - 재현성, 관제, 아티팩트, 안정성
  - baseline 추천 + ML plugin POC

- **V3**: 운영 고도화
  - worker/scheduler, model registry, governance/supervisor 확장
  - 실행 자동화, 품질 게이트 강화

---

### 마지막 경고

> **V2에서 가장 중요한 것은 “성능 향상”이 아니라 “깨지지 않는 실행 계약”이다.**
> 성능은 plugin POC로 검증하되, baseline과 contracts는 유지한다.
