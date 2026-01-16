# Quant Lab V2 — Streamlit Lab Console Philosophy

## Goals

- Streamlit UI는 **분석용 Lab Console** 역할만 수행한다.
- **실행(=CLI subprocess 호출, DB/아티팩트 생성)은 Run Center 한 곳에서만** 수행한다.
- 나머지 페이지는 DuckDB/SQLite/artifacts 기반의 **read-only 관측/검증/리서치 뷰**로 유지한다.

## Artifacts SSOT

- 실행으로 생성되는 모든 파일(예: `plan.json`, `pipeline.log`, 파생 YAML)은 반드시 `artifacts/runs/<run_id>/` 하위에 기록한다.
- 자동 생성/변형된 전략 YAML은 `artifacts/runs/<run_id>/generated/` 하위에 기록한다.
- 사람이 작성/관리하는 전략 원본은 `strategies/` 에만 존재한다.
- `strategies/generated/` 는 legacy로 간주하고 신규 생성은 중단한다.

## Run Identity (UUID vs Alias)

- `run_id`는 **UUID**이며 실행의 정체성(재현성/감사/경로) 기준이다.
  - 실행 산출물 경로는 항상 `artifacts/runs/<run_id>/` 이다.
- 사람이 읽기 쉬운 이름은 `run_slug`/`display_name`으로 제공한다.
  - 별칭 조회는 `artifacts/index/runs/<run_slug>.json`을 통해 `run_id`로 resolve 한다.
  - UI는 내부적으로 `run_id`를 기준으로 조회하고, 화면 표시에는 `display_name`을 사용한다.

## Plan → Run Link (추적용)

- Dry-run(Plan)과 실제 Run은 **서로 다른 ID/폴더**를 사용한다.
  - Plan: `artifacts/runs/<plan_id>/plan.json`
  - Run: `artifacts/runs/<run_id>/run.json` (run_id는 UUID)
- Run metadata(`run.json`)에는 추적을 위해 `plan_run_id`, `plan_artifacts_dir`가 포함될 수 있다.

## Machine-readable Progress

- Streamlit은 콘솔 텍스트를 파싱하지 않는다.
- 대신 `pipeline.log`에 기록되는 `PROGRESS_JSON:` 라인을 tail 하여 진행률/상태를 표시한다.
  - 예: recommend stage의 날짜별 targets 저장 이벤트

## Non-Goals (Anti-goals)

- 다른 페이지에서 `uv run quant ...`를 직접 호출하지 않는다.
- UI에서 DB 스키마/데이터를 생성하거나 수정하는 “관리 콘솔”로 확장하지 않는다.

## Responsibility Map (Pages)

- **Run Center**
  - 파이프라인/스테이지 실행 및 dry-run(계획 생성) 트리거의 단일 진입점
  - 운영 유틸 실행(예: `symbol-register`)도 Run Center에서만 트리거
  - 실행 로그 tail, 최근 runs/실패 목록 조회 (artifacts SSOT 우선)

- **Dashboard**
  - 전체 상태 요약(최근 runs, stage 상태, 최근 backtest, targets snapshot)
  - 실행 버튼은 두지 않는다(오직 Run Center 링크)

- **Data Center**
  - 심볼/가격 데이터 인벤토리 및 품질/커버리지 관측
  - 등록/ingest/features 실행 버튼은 두지 않는다

- **Feature Lab**
  - `features_daily` 기반 피처 분석/분포/상관/결측 탐색
  - 피처 계산 실행 버튼은 두지 않는다

- **Strategy Lab**
  - Strategy YAML 작성/검증/저장(원본은 `strategies/`)
  - `targets` 결과를 read-only로 조회/검토
  - dry-run/run 트리거는 두지 않는다(Plan/Run은 Run Center에서만)

- **Backtest Lab**
  - backtest 결과 탐색/비교/트레이드 분석
  - 재실행 트리거는 두지 않는다

- **Targets Analyzer**
  - 타깃/추천 결과 심화 분석(read-only)

## UX Rules

- 실행이 필요한 사용자는 어디서든 **Run Center로 유도**한다(페이지 링크 + 안내 문구).
- 페이지 상단에 “이 페이지의 목적”을 짧게 명시한다.

## Implementation Notes

- 실행 트리거 제거 대상: Dashboard/Data Center/Feature Lab/Strategy Lab/Backtest Lab
- 실행은 `app/ui/execution.py` 기반으로 Run Center에서만 수행
