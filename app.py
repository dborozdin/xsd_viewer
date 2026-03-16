"""XSD Schema Viewer — Streamlit application.

Visualizes XSD schemas in Altova XMLSpy notation.
Supports loading from GitHub URLs or uploading local files.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import streamlit as st

from core.xsd_parser import SchemaRegistry, parse_schema_with_imports
from core.svg_renderer import (
    render_element_diagram,
    render_overview_diagram,
    render_type_diagram,
)
from generate_doc import generate_html_for_schema
from github_fetcher import fetch_xsd_files, parse_github_url

# --- Bilingual labels ---

LABELS = {
    "en": {
        "title": "XSD Schema Viewer",
        "subtitle": "Visualize XSD schemas in Altova XMLSpy notation",
        "lang_toggle": "Русский",
        "source": "Data source",
        "source_github": "GitHub URL",
        "source_upload": "Upload files",
        "github_url": "GitHub folder URL",
        "github_url_help": "e.g. https://github.com/owner/repo/tree/main/xsd",
        "fetch": "Fetch",
        "fetching": "Fetching XSD files...",
        "fetched_ok": "Downloaded {n} file(s): {files}",
        "fetched_none": "No .xsd files found at this URL",
        "upload": "Upload XSD files",
        "schema_file": "Schema file",
        "viz_mode": "Visualization mode",
        "mode_element": "Element diagram",
        "mode_type": "Type diagram",
        "mode_overview": "Overview (all elements)",
        "element": "Element",
        "type": "Complex type",
        "depth": "Expansion depth",
        "tab_diagram": "Diagram",
        "tab_annotations": "Annotations",
        "no_files": "Upload XSD files or fetch from GitHub to get started.",
        "no_elements": "No elements found in this schema.",
        "no_types": "No complex types found in this schema.",
        "annotation_header": "Annotations for: {name}",
        "schema_annotation": "Schema description",
        "element_annotation": "Element annotation",
        "type_annotation": "Type annotation",
        "no_annotation": "No annotation available.",
        "error_fetch": "Error fetching files: {err}",
        "error_render": "Error rendering diagram: {err}",
        "render": "Render",
        "generate_doc": "Generate HTML doc",
        "generating_doc": "Generating documentation...",
        "download_doc": "Download HTML",
        "doc_depth": "Doc depth",
        "back_to_diagram": "Back to diagrams",
    },
    "ru": {
        "title": "Просмотр XSD-схем",
        "subtitle": "Визуализация XSD-схем в нотации Altova XMLSpy",
        "lang_toggle": "English",
        "source": "Источник данных",
        "source_github": "GitHub URL",
        "source_upload": "Загрузить файлы",
        "github_url": "URL папки на GitHub",
        "github_url_help": "напр. https://github.com/owner/repo/tree/main/xsd",
        "fetch": "Загрузить",
        "fetching": "Загрузка XSD-файлов...",
        "fetched_ok": "Загружено {n} файл(ов): {files}",
        "fetched_none": "Файлы .xsd не найдены по этому URL",
        "upload": "Загрузить XSD-файлы",
        "schema_file": "Файл схемы",
        "viz_mode": "Режим визуализации",
        "mode_element": "Диаграмма элемента",
        "mode_type": "Диаграмма типа",
        "mode_overview": "Обзор (все элементы)",
        "element": "Элемент",
        "type": "Сложный тип",
        "depth": "Глубина раскрытия",
        "tab_diagram": "Диаграмма",
        "tab_annotations": "Аннотации",
        "no_files": "Загрузите XSD-файлы или укажите URL на GitHub.",
        "no_elements": "В этой схеме нет элементов.",
        "no_types": "В этой схеме нет сложных типов.",
        "annotation_header": "Аннотации для: {name}",
        "schema_annotation": "Описание схемы",
        "element_annotation": "Аннотация элемента",
        "type_annotation": "Аннотация типа",
        "no_annotation": "Аннотация отсутствует.",
        "error_fetch": "Ошибка загрузки: {err}",
        "error_render": "Ошибка отрисовки: {err}",
        "render": "Построить",
        "generate_doc": "Сгенерировать HTML-описание",
        "generating_doc": "Генерация описания...",
        "download_doc": "Скачать HTML",
        "doc_depth": "Глубина описания",
        "back_to_diagram": "Назад к диаграммам",
    },
}


def _get_temp_dir() -> str:
    """Get or create a session-scoped temp directory."""
    if "temp_dir" not in st.session_state:
        st.session_state.temp_dir = tempfile.mkdtemp(prefix="xsd_viewer_")
    return st.session_state.temp_dir


def _get_registry() -> SchemaRegistry:
    """Get or create a session-scoped SchemaRegistry."""
    if "registry" not in st.session_state:
        st.session_state.registry = SchemaRegistry()
    return st.session_state.registry


def _reset_registry():
    """Reset the registry when files change."""
    st.session_state.registry = SchemaRegistry()


def _list_xsd_files() -> list[str]:
    """List .xsd files in the session temp directory."""
    tmp = _get_temp_dir()
    if not os.path.isdir(tmp):
        return []
    return sorted(f for f in os.listdir(tmp) if f.lower().endswith(".xsd"))


# Bundled demo schema — rich annotations, good for demonstration
_DEMO_SCHEMA = Path(__file__).parent / "examples" / "purchase.xsd"


def _load_demo_file():
    """Copy bundled demo XSD file on first session load."""
    if st.session_state.get("demo_loaded"):
        return
    try:
        if _DEMO_SCHEMA.exists():
            tmp = _get_temp_dir()
            shutil.copy(str(_DEMO_SCHEMA), os.path.join(tmp, "purchase.xsd"))
            st.session_state.demo_loaded = True
    except Exception:
        pass


def _collect_annotations(schema_path: str, name: str, mode: str, registry: SchemaRegistry) -> list[tuple[str, str]]:
    """Collect annotations for display in the Annotations tab.

    Returns list of (label, text) pairs.
    """
    annotations = []
    try:
        schema, _ = parse_schema_with_imports(schema_path)
    except Exception:
        schema = None

    if schema and schema.annotation and schema.annotation.documentation:
        annotations.append(("Schema", schema.annotation.documentation))

    if schema and mode == "element":
        elem = schema.find_element(name)
        if elem and elem.annotation and elem.annotation.documentation:
            annotations.append((f"Element: {name}", elem.annotation.documentation))
        if elem and elem.inline_type and elem.inline_type.annotation and elem.inline_type.annotation.documentation:
            annotations.append((f"Type of {name}", elem.inline_type.annotation.documentation))
    elif schema and mode == "type":
        ct = schema.find_complex_type(name)
        if ct and ct.annotation and ct.annotation.documentation:
            annotations.append((f"Type: {name}", ct.annotation.documentation))

    return annotations


def main():
    st.set_page_config(
        page_title="XSD Schema Viewer",
        page_icon=":mag:",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # --- Hide Streamlit chrome but keep sidebar toggle ---
    st.markdown(
        """<style>
        /* Hide the toolbar (Deploy button, app menu) */
        [data-testid="stToolbar"] { display: none !important; }
        #MainMenu { display: none !important; }
        footer { display: none !important; }
        /* Make header transparent and minimal — sidebar collapse button stays */
        header[data-testid="stHeader"] {
            background: transparent !important;
        }
        section[data-testid="stMain"] > div.block-container {
            padding-top: 1rem !important;
            padding-bottom: 0 !important;
        }
        section[data-testid="stSidebar"] > div {
            padding-top: 1rem !important;
        }
        /* Make iframe containers fill available height */
        [data-testid="stMain"] iframe {
            min-height: calc(100vh - 10rem) !important;
        }
        </style>""",
        unsafe_allow_html=True,
    )

    # --- Language toggle ---
    lang_ru = st.sidebar.toggle("🇷🇺 Русский", value=False, key="lang_ru")
    lang = "ru" if lang_ru else "en"
    L = LABELS[lang]

    st.title(L["title"])
    st.caption(L["subtitle"])

    # --- Load demo file on first visit ---
    _load_demo_file()

    # --- Sidebar: data source ---
    source = st.sidebar.radio(
        L["source"],
        [L["source_upload"], L["source_github"]],
        key="source_radio",
    )

    if source == L["source_github"]:
        github_url = st.sidebar.text_input(
            L["github_url"],
            value="https://github.com/dborozdin/word_to_s1000d/tree/main/xsd",
            help=L["github_url_help"],
            key="github_url",
        )
        if st.sidebar.button(L["fetch"], key="fetch_btn"):
            with st.spinner(L["fetching"]):
                try:
                    tmp = _get_temp_dir()
                    # Clean existing files
                    for f in os.listdir(tmp):
                        fp = os.path.join(tmp, f)
                        if os.path.isfile(fp):
                            os.remove(fp)
                    _reset_registry()

                    files = fetch_xsd_files(github_url, tmp)
                    if files:
                        st.sidebar.success(L["fetched_ok"].format(n=len(files), files=", ".join(files)))
                    else:
                        st.sidebar.warning(L["fetched_none"])
                except Exception as e:
                    st.sidebar.error(L["error_fetch"].format(err=str(e)))

    else:
        uploaded = st.sidebar.file_uploader(
            L["upload"],
            type=["xsd"],
            accept_multiple_files=True,
            key="file_uploader",
        )
        if uploaded:
            tmp = _get_temp_dir()
            # Clean existing files
            for f in os.listdir(tmp):
                fp = os.path.join(tmp, f)
                if os.path.isfile(fp):
                    os.remove(fp)
            _reset_registry()

            for f in uploaded:
                file_path = os.path.join(tmp, f.name)
                with open(file_path, "wb") as out:
                    out.write(f.getbuffer())

    # --- Schema file selector ---
    xsd_files = _list_xsd_files()

    if not xsd_files:
        st.info(L["no_files"])
        return

    selected_file = st.sidebar.selectbox(L["schema_file"], xsd_files, key="schema_file")
    schema_path = os.path.join(_get_temp_dir(), selected_file)

    # --- Parse schema for element/type lists ---
    registry = _get_registry()
    try:
        schema, registry = parse_schema_with_imports(schema_path)
        st.session_state.registry = registry
    except Exception as e:
        st.error(L["error_render"].format(err=str(e)))
        return

    # --- Visualization mode ---
    mode_options = [L["mode_element"], L["mode_type"], L["mode_overview"]]
    mode_label = st.sidebar.radio(L["viz_mode"], mode_options, key="viz_mode")

    if mode_label == L["mode_element"]:
        mode = "element"
    elif mode_label == L["mode_type"]:
        mode = "type"
    else:
        mode = "overview"

    # --- Element / Type selector ---
    selected_name = None

    if mode == "element":
        elem_names = [e.name for e in schema.elements]
        if not elem_names:
            st.warning(L["no_elements"])
            return
        default_idx = elem_names.index("Purchase") if "Purchase" in elem_names else 0
        selected_name = st.sidebar.selectbox(L["element"], elem_names, index=default_idx, key="element_select")

    elif mode == "type":
        type_names = [ct.name for ct in schema.complex_types]
        if not type_names:
            st.warning(L["no_types"])
            return
        selected_name = st.sidebar.selectbox(L["type"], type_names, key="type_select")

    # --- Depth slider ---
    depth = 2
    if mode != "overview":
        depth = st.sidebar.slider(L["depth"], 0, 5, 2, key="depth_slider")

    # --- Documentation generation ---
    st.sidebar.divider()
    doc_depth = st.sidebar.slider(L["doc_depth"], 0, 5, 2, key="doc_depth_slider")

    if st.sidebar.button(L["generate_doc"], key="gen_doc_btn", use_container_width=True):
        with st.spinner(L["generating_doc"]):
            try:
                html_content = generate_html_for_schema(schema_path, depth=doc_depth)
                doc_filename = Path(selected_file).stem + "_doc.html"
                doc_path = os.path.join(_get_temp_dir(), doc_filename)
                with open(doc_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                st.session_state.doc_html = html_content
                st.session_state.doc_filename = doc_filename
                st.session_state.show_doc = True
            except Exception as e:
                st.sidebar.error(L["error_render"].format(err=str(e)))

    # --- Render: documentation view or diagram view ---
    if st.session_state.get("show_doc") and st.session_state.get("doc_html"):
        # Documentation view — replaces diagrams
        col_back, col_download, col_spacer = st.columns([1, 1, 3])
        with col_back:
            if st.button(L["back_to_diagram"], key="back_to_diagram_btn", use_container_width=True):
                st.session_state.show_doc = False
                st.rerun()
        with col_download:
            st.download_button(
                L["download_doc"],
                data=st.session_state.doc_html,
                file_name=st.session_state.get("doc_filename", "schema_doc.html"),
                mime="text/html",
                key="download_doc_btn",
                use_container_width=True,
            )
        st.components.v1.html(st.session_state.doc_html, height=0, scrolling=True)
    else:
        # Diagram view
        tab_diagram, tab_annotations = st.tabs([L["tab_diagram"], L["tab_annotations"]])

        with tab_diagram:
            try:
                if mode == "element":
                    svg = render_element_diagram(schema_path, selected_name, depth, registry=registry)
                elif mode == "type":
                    svg = render_type_diagram(schema_path, selected_name, depth, registry=registry)
                else:
                    svg = render_overview_diagram(schema_path, registry=registry)

                diagram_html = f"""
                <div style="overflow: auto; background: white; border: 1px solid #ddd; border-radius: 4px; padding: 8px;">
                    {svg}
                </div>
                """
                st.components.v1.html(diagram_html, height=0, scrolling=True)

            except Exception as e:
                st.error(L["error_render"].format(err=str(e)))

        with tab_annotations:
            ann_name = selected_name or selected_file
            st.subheader(L["annotation_header"].format(name=ann_name))

            annotations = _collect_annotations(schema_path, ann_name, mode, registry)

            if annotations:
                for label, text in annotations:
                    st.markdown(f"**{label}**")
                    st.markdown(text)
                    st.divider()
            else:
                st.info(L["no_annotation"])


if __name__ == "__main__":
    main()
