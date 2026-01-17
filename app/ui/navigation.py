import streamlit as st

RUN_CENTER_PAGE = "pages/2_Run_Center.py"


def run_center_cta(
    *,
    title: str = "실행은 Run Center에서만 가능합니다.",
    body: str = "이 페이지는 분석/조회(read-only) 용도입니다.",
):
    st.info(f"{title} {body}")
    try:
        st.page_link(RUN_CENTER_PAGE, label="🏃 Run Center 열기")
    except Exception:
        st.caption("사이드바에서 'Run Center' 페이지로 이동하세요.")


def open_run_center(*, run_id: str | None = None, run_slug: str | None = None) -> None:
    """Navigate to Run Center with optional lookup parameters.

    Uses query params so Run Center can open run detail by canonical run_id.
    """

    try:
        if run_id:
            st.query_params["run_id"] = str(run_id)
        elif run_slug:
            st.query_params["run_slug"] = str(run_slug)
        st.switch_page(RUN_CENTER_PAGE)
    except Exception:
        # Fallback: user can navigate manually.
        if run_id:
            st.info(f"Run Center에서 run_id를 열어주세요: {run_id}")
