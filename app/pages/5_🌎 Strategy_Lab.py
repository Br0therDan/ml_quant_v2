import streamlit as st
import os
from datetime import datetime, timedelta
from streamlit_monaco import st_monaco

from src.quant.ui.services.strategy_files import (
    list_strategies,
    load_strategy_content,
    save_strategy_as,
)
from src.quant.ui.services import yaml_validate as yaml_validate
from app.ui.data_access import load_targets, load_targets_history
from app.ui.navigation import run_center_cta


def _get_yaml_validator():
    validate_with_warnings = getattr(
        yaml_validate, "validate_strategy_yaml_with_warnings", None
    )
    if validate_with_warnings is not None:
        return validate_with_warnings

    legacy_validate = getattr(yaml_validate, "validate_strategy_yaml", None)
    if legacy_validate is not None:

        def _wrapper(content: str):
            ok, errors = legacy_validate(content)
            return ok, errors, []

        return _wrapper

    raise ImportError(
        "No compatible YAML validator found in src.quant.ui.services.yaml_validate"
    )


validate_strategy_yaml_with_warnings = _get_yaml_validator()
extract_strategy_summary = yaml_validate.extract_strategy_summary


def _coerce_editor_text(value, fallback: str) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return fallback
    return str(value)


st.set_page_config(
    page_title="Strategy Lab | Quant Lab V2",
    page_icon="🌎",
    layout="wide",
)

st.title(
    "🌎 Strategy Lab",
    help="Strategy YAML authoring, validation, and target result viewing. Pipeline execution and dry-run are only available in Run Center.",
)
st.caption(
    "⚠️ 파이프라인 실행/드라이런은 Run Center에서만 가능합니다. Strategy Lab은 YAML 작성/검증과 결과(타깃) 조회 중심입니다."
)
# run_center_cta(
#     title="파이프라인 실행/드라이런은 Run Center에서만 가능합니다.",
#     body="Strategy Lab은 YAML 작성/검증과 결과(타깃) 조회 중심입니다.",
# )

# --- Session State Initialization ---
if "last_loaded_text" not in st.session_state:
    st.session_state["last_loaded_text"] = ""
if "current_file" not in st.session_state:
    st.session_state["current_file"] = None

# --- Layout: 2-Panel ---
col_controls, col_results = st.columns([0.3, 0.7])

with col_controls:
    with st.container(border=True, height="stretch"):
        st.subheader("Strategy Selection")

        # File Picker
        all_files = list_strategies()
        selected_file = st.selectbox(
            "Select Strategy YAML", all_files, index=0 if all_files else None
        )

        if selected_file != st.session_state["current_file"]:
            if selected_file is not None:
                content = load_strategy_content(selected_file)
                if content is not None:
                    st.session_state["last_loaded_text"] = content
                    st.session_state["monaco_content"] = content
                    st.session_state["current_file"] = selected_file

        # Action Buttons
        st.markdown("---")

        # Content Access for Buttons
        # Note: In a real app, we'd need a way to get the LATEST editor content
        # but st_monaco returns the current content on change.
        last_loaded_text = st.session_state["last_loaded_text"]
        editor_content = _coerce_editor_text(
            st.session_state.get("monaco_content"), fallback=last_loaded_text
        )
        is_dirty = editor_content != last_loaded_text

        is_valid, validation_errors, validation_warnings = (
            validate_strategy_yaml_with_warnings(editor_content)
        )

        # 1. Validate
        if st.button("🔍 Validate YAML", width="stretch"):
            if is_valid:
                st.success("YAML is valid!")
            else:
                for err in validation_errors:
                    st.error(err)
            for w in validation_warnings:
                st.warning(w)

        # 2. Save As
        with st.popover("💾 Save As...", width="stretch"):
            new_name = st.text_input("New Filename", placeholder="strategy_v2.yaml")
            if st.button("Confirm Save", type="primary"):
                if new_name:
                    if save_strategy_as(new_name, editor_content):
                        st.success(f"Saved to strategies/{os.path.basename(new_name)}")
                        st.session_state["last_loaded_text"] = editor_content
                        st.rerun()
                    else:
                        st.error("Save failed.")
                else:
                    st.warning("Enter a name.")

        st.markdown("---")
        if is_dirty:
            st.warning(
                "⚠️ 저장되지 않은 변경사항이 있습니다. 실행은 Run Center에서 하세요."
            )

        st.caption("실행/드라이런은 Run Center에서 동일 전략 YAML을 선택해 수행합니다.")

with col_results:
    with st.container(border=True, height=800):
        # --- Header Area ---
        last_loaded_text = st.session_state["last_loaded_text"]
        editor_content = _coerce_editor_text(
            st.session_state.get("monaco_content"), fallback=last_loaded_text
        )
        # Header area: Status Badges
        h1, h2, h3 = st.columns([0.7, 0.15, 0.15])
        with h1:
            st.subheader("YAML Editor")
        with h2:
            if is_dirty:
                st.warning("● UNSAVED")
            else:
                st.success("✓ SYNCED")
        with h3:
            if is_valid:
                st.info("VALID")
            else:
                st.error("INVALID")

        # Monaco Editor
        # Use key to persist and capture content
        with st.container(border=True):
            response = st_monaco(
                value=st.session_state["last_loaded_text"],
                language="yaml",
                height="400px",
                minimap=True,
                theme="vs-dark",
            )
            if response is not None:
                st.session_state["monaco_content"] = response

        editor_content = _coerce_editor_text(
            st.session_state.get("monaco_content"), fallback=last_loaded_text
        )
        is_valid, validation_errors, validation_warnings = (
            validate_strategy_yaml_with_warnings(editor_content)
        )

        # Validation Results
        if not is_valid:
            with st.expander("❌ Validation Errors", expanded=True):
                for err in validation_errors:
                    st.write(f"- {err}")

        if validation_warnings:
            with st.expander("⚠️ Validation Warnings", expanded=not is_valid):
                for w in validation_warnings:
                    st.write(f"- {w}")

        # Strategy Summary Card
        summary = extract_strategy_summary(editor_content)
        if summary:
            with st.container(border=True):
                st.markdown(f"**Strategy ID**: `{summary['id']}`")
                s1, s2, s3, s4 = st.columns(4)
                s1.metric("Universe", summary["universe"])
                s2.metric("Symbols", summary["symbols_count"])
                s3.metric("Signal", summary["signal"])
                s4.metric("Top-K", summary["top_k"])

            st.subheader("Targets (Read-only)")

            hist = load_targets_history(summary["id"])
            if hist.empty:
                st.info(
                    "아직 targets 결과가 없습니다. Run Center에서 recommend 단계를 실행해 생성하세요."
                )
            else:
                asof = st.selectbox(
                    "As-of",
                    options=sorted(hist["asof"].astype(str).unique(), reverse=True),
                    index=0,
                )

                df_targets = load_targets(summary["id"], asof)
                if df_targets.empty:
                    st.info("선택한 날짜에 targets가 없습니다.")
                else:
                    st.dataframe(
                        df_targets,
                        hide_index=True,
                        width="stretch",
                    )
