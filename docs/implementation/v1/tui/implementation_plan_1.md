# [Sprint 11] Interactive CLI UX/UI 고도화 계획

본 계획서는 기존의 명령어 기반(Typer) CLI 위에, 데이터 과학자가 직관적으로 파이프라인을 제어할 수 있는 **Interactive Mode (TUI)**를 도입하는 것을 목표로 합니다. 키보드 네비게이션, 컬러풀한 시각화, 그리고 실시간 모니터링 기능을 통해 사용자 경험을 극대화합니다.

## 1. 개요
복잡한 CLI 옵션(Flag)을 매번 기억하고 입력하는 수고를 덜기 위해, **방향키로 선택하고 엔터로 실행하는** 대화형 인터페이스를 구축합니다. `InquirerPy`와 `Rich` 라이브러리를 활용하여 모던하고 아름다운 터미널 경험을 제공합니다.

## 2. 핵심 설계 원칙
1.  **Dual Mode Support**: 기존의 `quant [command]` 방식(스크립트 자동화용)과 `quant interactive`(또는 `quant ui`) 방식(대화형 탐색용)을 모두 지원합니다.
2.  **Visual Excellence**: 중요한 정보는 **Bold/Color**로 강조하고, 테이블/패널을 적극 활용하여 정보의 구조를 명확히 합니다.
3.  **Workflow Guidance**: 사용자가 다음에 무엇을 해야 할지 자연스럽게 유도하는 흐름(Flow)을 설계합니다. (예: Ingest 완료 후 -> Features 생성 제안)

## 3. 주요 구현 기능

### 3.1 Main Menu (Interactive Hub)
- **Navigation**: 방향키(▲/▼)로 주요 모듈(Data, ML, Portfolio, System) 이동.
- **Shortcuts**: VIM 스타일 키바인딩(j/k) 및 숫자 단축키 지원.

### 3.2 Enhanced Input Experience
- **Fuzzy Search**: 심볼 선택 시(`AAPL`, `NVDA` 등) 타이핑으로 실시간 필터링 및 다중 선택(Multi-select).
- **Date Picker**: 달력 UI 또는 스마트 텍스트 입력 유효성 검사.
- **Spinners**: 작업 진행 중 Rich Spinner 및 Progress Bar 표시.

### 3.3 Advanced Features
- **Preset Management**: 자주 쓰는 파라미터 조합(예: "Quick Training")을 프리셋으로 저장 및 불러오기.
- **System Health Board**: 초기 실행 시 DB 연결, API 상태, 디스크 용량 등을 점검하는 대시보드 출력.

## 4. 구현 단계 (Progress Dashboard)

| 단계 | 작업 내용 | 상태 |
| :--- | :--- | :--- |
| Phase 1 | UI 라이브러리(`InquirerPy`) 설정 및 메인 메뉴 구조 설계 | [ ] |
| Phase 2 | 모듈별(Data, Features, Train, Backtest) 인터랙티브 워크플로우 구현 | [ ] |
| Phase 3 | Rich 기반 컬러 로깅 및 시스템 헬스 체크 기능 통합 | [ ] |

## 5. 기술 스택 제안
- **Input/Prompt**: `InquirerPy` (가볍고 강력한 Python 프롬프트 라이브러리)
- **Output/Display**: `Rich` (이미 도입됨 - 활용도 극대화)
- **CLI Framework**: `Typer` (기존 유지)

## 6. 예상 산출물 (Artifacts)
- `src/quant/interactive.py`: 대화형 로직의 핵심 진입점.
- `quant ui` 명령어: 새로운 사용자 경험의 시작.
