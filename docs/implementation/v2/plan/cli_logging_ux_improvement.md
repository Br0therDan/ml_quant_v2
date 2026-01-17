# CLI 로깅 및 UX 개선 계획서 (Quant Lab V2)

- 버전: 1.0.0
- 작성일: 2026-01-17
- 상태: **승인 대기**

## 1. 문제 식별 (Problem Identification)

현재 파이프라인 실행 시 발생하는 로깅 시스템은 다음과 같은 사용자 경험(UX) 문제를 가지고 있습니다.

1.  **터미널 오염 (Log Spamming)**:
    -   100개 이상의 심볼 처리가 기본인 시스템에서 개별 심볼마다 발생하는 `INFO` 로그가 터미널을 가득 채워 정작 중요한 단계별 요약을 확인하기 어려움.
    -   `PROGRESS_JSON`과 같은 기계 가독성 데이터가 CLI 사용자에게 직접 노출됨.
2.  **진행 상태 가시성 부족**:
    -   텍스트가 빠르게 스크롤되어 현재 전체 공정 중 어느 위치에 있는지 시각적으로 파악하기 힘듦.
3.  **로그 레벨 혼용**:
    -   심볼 처리 완료, 데이터 저장 등 상세 분석에 필요한 정보가 `INFO` 레벨로 설정되어 있어, 일반 실행 모드에서도 과도한 노이즈를 발생시킴.
4.  **UI/CLI 간섭**:
    -   Streamlit UI를 위한 진행률 출력이 CLI 환경에서도 동일하게 출력되어 사용자 친화성이 떨어짐.

## 2. 개선 목표 (Objectives)

-   **Zero Spam**: 일반 실행 시 심볼 단위의 상세 로그를 노출하지 않음.
-   **Visual Progress**: `rich` 라이브러리를 활용한 단계별 프로그래스 바 도입.
-   **Clear Milestones**: 파이프라인의 주요 스테이지(Stage) 전환을 명확히 표시.
-   **UI-Safe separation**: `PROGRESS_JSON` 출력을 CLI에서 분리하고 파일 및 UI 전용 스트림으로 관리.

## 3. 세부 이행 계획 (Action Plan)

### 3.1 로그 레벨 최적화 (Log Level Downgrade)
-   **대상 파일**: 
    -   [src/quant/data_curator/ingest.py](src/quant/data_curator/ingest.py)
    -   [src/quant/feature_store/features.py](src/quant/feature_store/features.py)
    -   [src/quant/feature_store/labels.py](src/quant/feature_store/labels.py)
    -   [src/quant/ml/scorer.py](src/quant/ml/scorer.py)
-   **변경 사항**: 개별 심볼 처리 시작/완료 메시지(`logger.info`)를 `logger.debug`로 일괄 격하.

### 3.2 오케스트레이터 로깅 정책 강화
-   **파일**: [src/quant/batch_orchestrator/pipeline.py](src/quant/batch_orchestrator/pipeline.py)
-   **변경 사항**:
    -   각 Stage 시작 시 `rich.console`을 사용하여 굵고 선명한 헤더 출력.
    -   실행 도중 하위 모듈의 로거(`quant.*`) 레벨을 일시적으로 `WARNING`으로 설정하여 노이즈 차단.
    -   `--verbose` 플래그가 있을 경우에만 서비스 레벨의 `DEBUG` 로그 노출.

### 3.3 Rich Progress Bar 전면 도입
-   `ingest`, `features`, `labels` 루프에 `rich.progress`를 적용.
-   **TTY 감지**: 터미널 환경이 아닐 경우(Streamlit 파이프 등)에는 `rich` 출력을 생략하여 호환성 유지.

### 3.4 Progress JSON 은닉 및 필터링
-   **Orchestrator**: `_write_progress_json`은 파일에만 기록 (실행 중 터미널에 노출되지 않도록 유지).
-   **UI (Run Center)**: [app/pages/2_▶️ Run_Center.py](app/pages/2_▶️ Run_Center.py)의 로그 조회 섹션에서 `PROGRESS_JSON`으로 시작하는 모든 라인을 필터링하여 사용자에게 '진짜 로그'만 노출.
-   **Frequency**: 반복이 심한 루프(예: recommendation dates)에서는 매건 기록 대신 일정 간격(예: 10% 단위 또는 10건 단위)으로 `PROGRESS_JSON`을 기록하도록 최적화 검토 (현재는 매건 기록 중).

## 4. 기대 효과 (Expected Outcomes)

-   수백 개의 심볼을 처리하더라도 터미널은 깔끔하게 현재 실행 중인 스테이지의 요약 정보와 진행률 바만 표시하게 됨.
-   실제 오류 발생 시 노이즈에 묻히지 않고 빠른 식별 가능.
-   전문적인 CLI 도구로서의 사용자 신뢰도 향상.

---

**승인 요청**: 위 계획에 동의하시면 작업을 시작하도록 하겠습니다.
