# Walkthrough: V2 Phase P1 - Meta DB(SQLModel) & Run Registry

## 1. 개요
V2 시스템 전환의 첫 단계인 Phase P1을 완료하였습니다. SQLite를 활용한 메타데이터 관리 시스템과 모든 CLI 실행을 추적하는 Run Registry를 구축하였습니다.

## 2. 주요 변경 사항

### 2.1 SQLite Meta DB (SQLModel)
- [src/quant/models/meta.py](file:///Users/donghakim/ml_quant/src/quant/models/meta.py)에 SQLModel 기반의 테이블 정의
    - `symbols`: 유니버스 관리
    - `experiments`: 실험 설정 관리
    - `models`: 학습된 모델 레지스트리
    - `runs`: 실행 로그 (Run Registry용)

### 2.2 Run Registry 구현
- [src/quant/repos/run_registry.py](file:///Users/donghakim/ml_quant/src/quant/repos/run_registry.py) 추가
- 모든 CLI 실행 시 UUID 기반의 `run_id` 생성 및 시작/종료/에러 상태 기록

### 2.3 `quant init-db` 고도화
- DuckDB: [schema_duck.sql](file:///Users/donghakim/ml_quant/src/quant/db/schema_duck.sql)을 실행하여 시계열 및 산출물 테이블(targets 등 포함) 생성
- SQLite: `SQLModel.metadata.create_all()`을 사용하여 메타 테이블 생성
- 초기화 과정 자체를 `runs` 테이블에 기록 (정상 완료 시 [success](file:///Users/donghakim/ml_quant/src/quant/repos/run_registry.py#27-37))

## 3. 검증 결과

### 3.1 DB 초기화 및 Run 기록
`quant init-db` 실행 시 SQLite에 로그가 정상적으로 남는 것을 확인하였습니다.

```bash
uv run quant init-db
# ...
# Run ID: 16ec1d2c-5462-4c8a-8b62-325fa0b9bdb3
# ...
```

SQLite `runs` 테이블 조회 결과:
```sql
SELECT run_id, kind, status FROM runs;
-- ('16ec1d2c-5462-4c8a-8b62-325fa0b9bdb3', 'init-db', 'success')
```

### 3.2 일반 CLI 실행 기록
`quant config` 실행 시에도 자동으로 로그가 남는 것을 확인하였습니다.

```bash
uv run quant config
# ...
# Runs in DB: [('88a19ce5-4d2e-4845-9279-9614fb46c03a', 'config', 'success')]
```

## 4. 관련 파일
- [meta.py](file:///Users/donghakim/ml_quant/src/quant/models/meta.py): SQLModel 정의
- [run_registry.py](file:///Users/donghakim/ml_quant/src/quant/repos/run_registry.py): 기록 로직
- [cli.py](file:///Users/donghakim/ml_quant/src/quant/cli.py): CLI 연동부
- [schema_duck.sql](file:///Users/donghakim/ml_quant/src/quant/db/schema_duck.sql): DuckDB 스키마
- [RUNBOOK.md](file:///Users/donghakim/ml_quant/docs/implementation/v2/RUNBOOK.md): 업데이트된 운영 가이드
