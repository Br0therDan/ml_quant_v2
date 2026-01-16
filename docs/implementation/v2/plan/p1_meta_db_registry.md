# Sprint Implementation Plan: V2 Phase P1 - Meta DB(SQLModel) & Run Registry

**Version:** v1.0.0  
**Date:** 2026-01-15  
**Last Updated:** 2026-01-15

---

## 1. Executive Summary
V2 시스템의 기반이 되는 SQLite Meta DB를 SQLModel 기반으로 구축하고, 모든 CLI 실행을 추적하기 위한 Run Registry를 구현한다. 이는 V2 SSOT 문서들(`V2_SYSTEM_SPEC.md`, `DB_SCHEMA.md`)에서 정의한 계약을 철저히 준수한다.

---

## 2. Objective
- SQLite 기반 Meta DB 구축 (`symbols`, `experiments`, `models`, `runs`)
- `quant init-db` 명령을 통한 SQLite 및 DuckDB 초기화 자동화
- `RunRegistry`를 통한 실행 로그 기록 시스템 구축
- 모든 CLI 실행 시 `run_id` 생성 및 `runs` 테이블 기록 보장

---

## 3. Progress Dashboard

| Phase | Scope | Status |
|---|---|---|
| P1-1 | Meta DB Schema Definition | [ ] |
| P1-2 | DB Engine & Session Utility | [ ] |
| P1-3 | Run Registry Logic | [ ] |
| P1-4 | CLI Integration (init-db & Logging) | [ ] |
| P1-5 | Verification & Documentation | [ ] |

---

## 4. Implementation Plan

### 4.1 Meta DB Schema Definition (SQLModel)
- [ ] `src/quant/models/meta.py` 생성
- [ ] `Symbol`, `Experiment`, `Model`, `Run` 클래스 정의 (SQLModel)
- [ ] `DB_SCHEMA.md`의 데이터 타입 및 제약 조건 준수

### 4.2 DB Engine & Session Utility
- [ ] `src/quant/db/engine.py` 수정/생성
- [ ] SQLite용 `sqlite_engine` 및 DuckDB용 `duckdb_conn` 관리
- [ ] `get_session()` 컨텍스트 매니저 제공 (SQLModel Session)

### 4.3 Run Registry Logic
- [ ] `src/quant/repos/run_registry.py` 생성/수정
- [ ] `run_start(kind, config)`: 새로운 run 생성 및 ID 반환
- [ ] `run_success(run_id)`: 상태를 SUCCESS로 업데이트
- [ ] `run_fail(run_id, error)`: 상태를 FAIL로 업데이트하고 에러 기록

### 4.4 CLI Integration
- [ ] `src/quant/cli.py` 수정
- [ ] `init_db` 커맨드 구현
    - DuckDB: 고정 스키마 SQL 실행 (필요 시 `src/quant/db/schema.sql` 로딩)
    - SQLite: `SQLModel.metadata.create_all(engine)` 호출
- [ ] CLI 실행 래퍼(Wrapper) 또는 데코레이터 검토 (모든 명령에 Run 기록 자동화)

### 4.5 Verification & Documentation
- [ ] P1 단위 테스트 또는 검증 스크립트 작성
- [ ] `docs/implementation/v2/RUNBOOK.md`에 P1 검증 절차 추가

---

## 5. Expected Artifacts
- `src/quant/models/meta.py` [NEW]
- `src/quant/db/engine.py` [MODIFY/NEW]
- `src/quant/repos/run_registry.py` [NEW]
- `src/quant/cli.py` [MODIFY]
- `docs/implementation/v2/walkthrough/p1_meta_db_walkthrough.md` [NEW]

---

## 6. Done Criteria
- `quant init-db` 실행 성공
- SQLite `data/meta.db` 생성 및 4개 테이블 확인
- CLI 실행 시 `runs` 테이블에 로그가 기록되는지 확인
