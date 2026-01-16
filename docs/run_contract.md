# Run Contract v1.1 — `quant pipeline run`

이 문서는 `quant pipeline run`의 **실행 계약(Contract)** 을 정의합니다.

## 목표

- `--dry-run`은 **절대 실행하지 않고 계획(Plan)만 출력**합니다.
  - DuckDB/SQLite write 금지
  - 외부 API 호출 금지
  - 대신: 입력 검증 + YAML 파싱 + universe/stage resolve + (옵션) read-only 점검(warnings)

## Dry-run 출력 규약

- stdout에 반드시 1줄 포함:
  - `PLAN_JSON: {...}` (JSON은 1줄이며 파싱 가능)
- 또한 파일을 저장:
  - `artifacts/runs/<run_id>/plan.json`

## Run (non dry-run) 출력/저장 규약

- **정체성(Identity)**
  - canonical `run_id`는 반드시 UUID이며 불변이다.
  - 사용자가 `--run-id`에 UUID가 아닌 값을 주면, 이는 **run_slug(별칭)** 으로 취급되고 실행용 UUID `run_id`는 새로 생성된다.
  - 사람이 읽기 쉬운 이름이 필요하면 `run_slug`/`display_name`을 사용한다.
- 저장 위치(SSOT): `artifacts/runs/<run_id>/`
  - `run.json` (파이프라인 메타)
  - `pipeline.log`
  - `stages/<stage>/result.json`
- 별칭 인덱스(lookup): `artifacts/index/runs/<run_slug>.json`
  - `run_slug`는 기본적으로 다음 구성으로 결정된다.
    - `<strategy_id>__<from>_<to>__<stages_short>__<universe_hint>`
  - 동일 `run_slug`가 다른 `run_id`로 이미 사용 중이면 `__<run_id_prefix>` suffix를 붙여 충돌을 회피한다.

### run.json 주요 필드

- `run_id`, `run_slug`, `display_name`
- `status` (running/success/fail), `started_at`, `ended_at`, `exit_code`
- `strategy_id`, `strategy_version`, `strategy_path`
- `date_from`, `date_to`
- `symbols_resolved`, `stages_resolved`
- `stage_results[]`: 각 stage의 `stage_exec_id`, `status`, `result_path`, `meta`
- (옵션) Plan 링크: `plan_run_id`, `plan_artifacts_dir`
  - UI/오케스트레이터가 Plan→Run 흐름을 추적할 때 사용
  - 예: `plan_run_id=plan_...`, `plan_artifacts_dir=artifacts/runs/plan_.../`

### stage result.json 표준 스키마

`artifacts/runs/<run_id>/stages/<stage>/result.json`은 아래를 포함한다(추가 필드는 허용).

- `ok` (boolean)
- `stage_name`, `status`, `stage_exec_id`
- `started_at`, `ended_at`, `elapsed_sec`
- `errors[]`, `warnings[]`
- `meta` (UI 파싱용)

### 진행 이벤트(PROGRESS_JSON)

- 대량 루프 작업(예: recommend 날짜별 targets 저장)은 `pipeline.log`에 머신리더블 라인을 append한다.
  - 예: `PROGRESS_JSON: {"stage":"recommend","event":"targets_write",...}`

### Plan JSON 필드

필드는 아래를 포함합니다(추가 필드는 허용).

- `run_id` (dry-run이라도 생성, `plan_` prefix)
- `invoked_command`
- `strategy_path`
- `strategy_id`, `strategy_version`
- `date_from`, `date_to`
- `stages_requested`, `stages_resolved`
- `symbols_override`, `symbols_resolved`
- `dry_run=true`
- `fail_fast`
- `validation.ok`, `validation.errors[]`, `validation.warnings[]`
- `artifacts_dir` (예: `artifacts/runs/<run_id>/`)

## 입력 정규화/검증

- 날짜: `YYYY-MM-DD`, 그리고 `from <= to`
- stages: 허용값만 통과
  - `ingest, features, labels, recommend, backtest`
  - 공백 제거, 중복 제거, 소문자 normalize
- symbols override:
  - `--symbols AAPL,PLTR,QQQM` 또는 `--symbols AAPL --symbols PLTR` 모두 허용
  - 콤마 split, 공백 제거, 대문자 normalize, 중복 제거

## 로컬 재현(Acceptance Tests)

### A/B/C: symbols_resolved가 달라야 하고 PLAN_JSON + plan.json이 있어야 함

```bash
# 1) strategy universe 기반
quant pipeline run \
  --strategy strategies/example.yaml \
  --from 2024-01-01 \
  --to 2024-01-10 \
  --dry-run

# 2) symbols override 기반
quant pipeline run \
  --strategy strategies/example.yaml \
  --from 2024-01-01 \
  --to 2024-01-10 \
  --symbols AAPL,PLTR,QQQM \
  --dry-run

# 출력에서 PLAN_JSON: 라인을 확인하고,
# 해당 run_id로 artifacts/runs/<run_id>/plan.json 파일 생성 여부를 확인합니다.
```

### D: stages subset

```bash
quant pipeline run \
  --strategy strategies/example.yaml \
  --from 2024-01-01 \
  --to 2024-01-10 \
  --stages recommend,backtest \
  --dry-run
```

### E: 잘못된 stage는 시작 전에 실패

```bash
quant pipeline run \
  --strategy strategies/example.yaml \
  --from 2024-01-01 \
  --to 2024-01-10 \
  --stages foo \
  --dry-run

# exit code != 0 이어야 합니다.
```
