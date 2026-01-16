# Run Center Demo Walkthrough (V2)
- Version: v2.0.0
- Created: 2026-01-16
- Last Updated: 2026-01-16

## 1. Executive Summary

이 문서는 Quant Lab V2의 **Run Center(단일 실행 진입점)** 를 사용해
1) Plan(dry-run) 생성 → 2) validation gate 통과 후 Run(UUID) 실행 → 3) artifacts SSOT 기반 관측(로그/진행/스테이지 결과) → 4) alias(run_slug)로 조회
흐름을 빠르게 검증하기 위한 데모 스크립트입니다.

## 2. Objective

- Run Contract 준수 확인
  - `--dry-run`은 실행 금지(외부 API/DB write 금지) + `PLAN_JSON` 1줄 + `artifacts/runs/<plan_id>/plan.json` 생성
  - Run은 UUID `run_id`로 `artifacts/runs/<run_id>/`에 `run.json`, `pipeline.log`, `stages/*/result.json`를 SSOT로 생성
- UI 비협상 조건 준수 확인
  - 실행 트리거는 Run Center에서만
  - 관측은 artifacts 기반(텍스트 파싱 최소화, `PROGRESS_JSON:` 기반)

## 3. Progress Dashboard

| 항목            | 기대 결과                              | 확인 방법                                 | 상태 |
| --------------- | -------------------------------------- | ----------------------------------------- | ---- |
| Plan 생성       | `PLAN_JSON` + `plan.json` 저장         | CLI `--dry-run` 또는 Run Center Plan 버튼 | ☐    |
| Validation Gate | `validation.ok=true`일 때만 Run 활성화 | Run Center UI 버튼 disabled 상태          | ☐    |
| Run UUID        | Run은 항상 UUID 폴더                   | `artifacts/runs/<uuid>/` 생성 확인        | ☐    |
| run.json        | 시작 즉시 `status=running`             | Run Center Run View + 파일 확인           | ☐    |
| Progress        | `PROGRESS_JSON:` 이벤트 표시           | Run Center progress bar / 이벤트 카드     | ☐    |
| Stage results   | `stages/<stage>/result.json` 표시      | Run View Stage cards                      | ☐    |
| Alias lookup    | run_slug로 run_id resolve              | Run Center deep link / 검색               | ☐    |

## 4. Implementation Plan (체크리스트)

- [ ] (준비) Streamlit 실행: `uv run streamlit run app/main.py`
- [ ] (Plan) Run Center에서 strategy/date/stages 선택 후 `Dry Run (Plan)` 실행
- [ ] (검증) Plan View에서 `validation.ok=true` 확인
- [ ] (Run) `Run (Execute)` 실행 후 생성된 `run_id(UUID)` 확인
- [ ] (관측) Run View에서 `run.json`, `pipeline.log`, `PROGRESS_JSON` 진행/스테이지 결과 확인
- [ ] (조회) run_slug(별칭)로 Run을 다시 열어 동일 run_id로 resolve 되는지 확인

---

## 데모 상세 절차

### A) Streamlit 실행

```bash
uv run streamlit run app/main.py
```

### B) Plan(dry-run)

- 페이지: **Run Center**
- Strategy: `strategies/example.yaml` (또는 유효한 YAML)
- Date: 임의 범위(예: 2025-01-01 ~ 2025-01-10)
- Stages: 가볍게 `features`만 선택(환경에 따라 조정)
- 클릭: `Dry Run (Plan)`

기대:
- Plan View에 구조화된 Plan 표시
- `artifacts/runs/<plan_id>/plan.json` 생성

### C) Validation Gate

기대:
- `validation.ok=true`가 아니면 Run 버튼이 비활성화

### D) Run(UUID)

- 클릭: `Run (Execute)`

기대:
- UI가 UUID `run_id`를 생성
- `artifacts/runs/<run_id>/run.json`이 즉시 생성되고 `status=running`
- `pipeline.log`, `exit_code.txt`, `pipeline.pid`가 동일 폴더에 생성

### E) 관측(artifacts-first)

- Run View에서 확인
  - `run.json` summary
  - `pipeline.log` tail
  - `PROGRESS_JSON:` 기반 진행 이벤트
  - `stages/<stage>/result.json` 카드

### F) Alias(별칭)로 조회

- Run View에 `run_slug`가 존재하는 경우
  - `artifacts/index/runs/<run_slug>.json`이 생성되어 있어야 함
  - Run Center에서 run_slug로 검색/열기 시 canonical `run_id`로 resolve

---

## 트러블슈팅(요약)

- `Run`이 즉시 실패할 경우:
  - `artifacts/runs/<run_id>/pipeline.log` 확인
  - `exit_code.txt` 확인
- Plan에서 `validation.ok=false`일 경우:
  - Strategy YAML 스키마/필수 필드 확인 (`strategy_id/version/universe/rebalance/portfolio/supervisor` + `signal|recommender`)
