# Walkthrough - Batch Orchestrator (P7)

## 1. 개요
P7 단계에서는 전체 데이터 파이프라인(Ingest → Features → Labels → Recommend → Backtest)을 단일 커맨드로 실행할 수 있는 **Batch Orchestrator**를 구현했습니다.

## 2. 주요 기능
- **단일 CLI 커맨드**: `quant pipeline run` 하나로 End-to-End 실행
- **Fail-Fast**: 어느 단계든 실패 시 즉시 중단 (옵션으로 제어 가능)
- **통합 로깅**: 모든 실행 단계(Stage)와 부모 파이프라인 실행이 SQLite [runs](file:///Users/donghakim/ml_quant/app/ui/data_access.py#54-64) 테이블에 기록됨
- **유연한 구성**: 특정 단계만 실행(`--stages`)하거나 전략 파일(`--strategy`) 기반으로 동작

## 3. 사용 예시

### 3.1 전체 파이프라인 실행
```bash
uv run quant pipeline run \
  --strategy strategies/example.yaml \
  --from 2025-01-01 \
  --to 2025-12-31 \
  --symbols AAPL
```

### 3.2 특정 단계만 실행 (예: Ingest 및 Feature 계산만)
```bash
uv run quant pipeline run \
  --strategy strategies/example.yaml \
  --from 2025-01-01 \
  --to 2025-12-31 \
  --stages ingest,features
```

### 3.3 Dry Run (실행 계획 확인)
```bash
uv run quant pipeline run \
  --strategy strategies/example.yaml \
  --from 2025-01-01 \
  --to 2025-12-31 \
  --dry-run
```

## 4. 구조 변경 사항
- **New Module**: [src/quant/batch_orchestrator/pipeline.py](file:///Users/donghakim/ml_quant/src/quant/batch_orchestrator/pipeline.py) (파이프라인 로직)
- **New Repo**: [src/quant/repos/targets.py](file:///Users/donghakim/ml_quant/src/quant/repos/targets.py) ([save_targets](file:///Users/donghakim/ml_quant/src/quant/repos/targets.py#11-101) 로직 분리 및 스키마 강화)
- **CLI**: [src/quant/cli.py](file:///Users/donghakim/ml_quant/src/quant/cli.py)에 [pipeline](file:///Users/donghakim/ml_quant/src/quant/cli.py#553-606) 커맨드 그룹 추가

## 5. 트러블슈팅
- **DuckDB Lock**: 파이프라인은 DB 쓰기 작업을 수행하므로, **Streamlit 앱이 실행 중일 때는 Lock 에러가 발생**할 수 있습니다. 배치 실행 전에는 Streamlit을 종료하거나 읽기 전용으로 설정해야 합니다.
