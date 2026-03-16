#!/usr/bin/env python3
"""Generate HTML documentation for any XSD schema with embedded SVG diagrams.

Auto-discovers all global elements, types, and annotations — no hardcoded
schema knowledge required.

Usage:
    python generate_doc.py examples/purchase.xsd
    python generate_doc.py schema.xsd -o docs/schema.html -d 3
    python generate_doc.py schema.xsd --elements Root Child1 Child2
    python generate_doc.py schema.xsd --lang ru
"""
from __future__ import annotations

import argparse
import html as html_mod
import sys
from pathlib import Path

from core.xsd_parser import parse_schema_with_imports
from core.svg_renderer import (
    render_element_diagram,
    render_overview_diagram,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate HTML documentation for an XSD schema.",
    )
    p.add_argument("schema_path", help="Path to the XSD file")
    p.add_argument("-o", "--output", help="Output HTML path (default: <schema>_doc.html)")
    p.add_argument("-d", "--depth", type=int, default=2, help="Diagram expansion depth (default: 2)")
    p.add_argument("--elements", nargs="+", metavar="NAME", help="Elements to diagram (default: all global)")
    p.add_argument("--no-overview", action="store_true", help="Skip overview diagram")
    p.add_argument("--title", help="Custom document title")
    p.add_argument("--lang", default="", help="Preferred annotation language (e.g. 'en', 'ru')")
    return p.parse_args(argv)


def _esc(text: str) -> str:
    return html_mod.escape(text)


def _get_title(schema, custom_title: str | None, schema_path: str, lang: str = "") -> str:
    if custom_title:
        return custom_title
    if schema.annotation and schema.annotation.has_content():
        doc = schema.annotation.get_doc(lang).strip()
        first = doc.split(".")[0].strip()
        if first:
            return first
    stem = Path(schema_path).stem.replace("_", " ").replace("-", " ")
    return f"{stem.title()} Schema"


def _build_header(title: str, schema, lang: str = "") -> str:
    parts = [f'  <header>\n    <h1>{_esc(title)}</h1>']
    if schema.annotation and schema.annotation.has_content():
        parts.append(f'    <p class="description">{_esc(schema.annotation.get_doc(lang).strip())}</p>')
    parts.append("  </header>")
    return "\n".join(parts)


def _build_overview(schema_path: str, registry, lang: str = "") -> str:
    svg = render_overview_diagram(schema_path, registry=registry, lang=lang)
    return (
        '  <section>\n'
        '    <h2>Overview</h2>\n'
        '    <p>All top-level elements defined in the schema.</p>\n'
        f'    <div class="diagram">{svg}</div>\n'
        '  </section>'
    )


def _build_element_section(schema_path: str, elem, depth: int, registry, lang: str = "") -> str:
    svg = render_element_diagram(schema_path, elem.name, depth, registry=registry, lang=lang)
    parts = [
        "  <section>",
        f"    <h2>{_esc(elem.name)}</h2>",
    ]
    if elem.annotation and elem.annotation.has_content():
        parts.append(f'    <p class="description">{_esc(elem.annotation.get_doc(lang).strip())}</p>')
    if elem.type_ref:
        parts.append(f'    <p class="meta">Type: <code>{_esc(elem.type_ref)}</code></p>')
    parts.append(f'    <div class="diagram">{svg}</div>')
    parts.append("  </section>")
    return "\n".join(parts)


def _build_simple_types_table(schema, lang: str = "") -> str:
    if not schema.simple_types:
        return ""
    rows = []
    for st in schema.simple_types:
        enums = ", ".join(st.enumerations) if st.enumerations else ""
        annotation = ""
        if st.annotation and st.annotation.has_content():
            annotation = _esc(st.annotation.get_doc(lang).strip())
        rows.append(
            f"        <tr>"
            f"<td><code>{_esc(st.name)}</code></td>"
            f"<td>{_esc(st.restriction_base)}</td>"
            f"<td>{_esc(enums)}</td>"
            f"<td>{annotation}</td>"
            f"</tr>"
        )
    return (
        '  <section>\n'
        '    <h2>Simple Types</h2>\n'
        '    <table>\n'
        '      <thead>\n'
        '        <tr><th>Type</th><th>Base</th><th>Values</th><th>Description</th></tr>\n'
        '      </thead>\n'
        '      <tbody>\n'
        + "\n".join(rows) + "\n"
        '      </tbody>\n'
        '    </table>\n'
        '  </section>'
    )


def generate_html_for_schema(
    schema_path: str,
    *,
    depth: int = 2,
    elements: list[str] | None = None,
    no_overview: bool = False,
    title: str | None = None,
    lang: str = "",
) -> str:
    """Generate HTML documentation for a schema file.

    Can be called programmatically (from Streamlit app, etc.) or via CLI.
    """
    schema_path = str(Path(schema_path).resolve())
    schema, registry = parse_schema_with_imports(schema_path)

    doc_title = _get_title(schema, title, schema_path, lang=lang)

    sections: list[str] = []
    sections.append(_build_header(doc_title, schema, lang=lang))

    if not no_overview:
        sections.append(_build_overview(schema_path, registry, lang=lang))

    elem_names = elements if elements else [e.name for e in schema.elements]

    for name in elem_names:
        elem = schema.find_element(name)
        if elem:
            sections.append(_build_element_section(schema_path, elem, depth, registry, lang=lang))
        else:
            print(f"Warning: element '{name}' not found in schema, skipping.", file=sys.stderr)

    types_html = _build_simple_types_table(schema, lang=lang)
    if types_html:
        sections.append(types_html)

    body = "\n\n".join(sections)

    html_lang = lang if lang else "en"
    return HTML_TEMPLATE.format(title=_esc(doc_title), body=body, html_lang=html_lang)


def generate_html(args: argparse.Namespace) -> str:
    return generate_html_for_schema(
        args.schema_path,
        depth=args.depth,
        elements=args.elements,
        no_overview=args.no_overview,
        title=args.title,
        lang=args.lang,
    )


HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="{html_lang}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    :root {{
      --bg: #fafafa;
      --fg: #222;
      --accent: #2c5282;
      --border: #e2e8f0;
    }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
      background: var(--bg);
      color: var(--fg);
      max-width: 960px;
      margin: 0 auto;
      padding: 2rem 1.5rem;
      line-height: 1.6;
    }}
    h1 {{
      font-size: 1.8rem;
      color: var(--accent);
      border-bottom: 2px solid var(--accent);
      padding-bottom: 0.5rem;
      margin-bottom: 1rem;
    }}
    h2 {{
      font-size: 1.3rem;
      color: var(--accent);
      margin-top: 2rem;
      margin-bottom: 0.5rem;
      border-bottom: 1px solid var(--border);
      padding-bottom: 0.3rem;
    }}
    .description {{
      margin-bottom: 0.3rem;
    }}
    .meta {{
      font-size: 0.9em;
      color: #555;
      margin-bottom: 0.5rem;
    }}
    .diagram {{
      margin: 1rem 0;
      padding: 1rem;
      background: #fff;
      border: 1px solid var(--border);
      border-radius: 6px;
      overflow-x: auto;
    }}
    .diagram svg {{
      max-width: 100%;
      height: auto;
    }}
    table {{
      border-collapse: collapse;
      margin: 1rem 0;
      width: 100%;
    }}
    th, td {{
      border: 1px solid var(--border);
      padding: 0.5rem 0.75rem;
      text-align: left;
    }}
    th {{
      background: #edf2f7;
      font-weight: 600;
    }}
    code {{
      background: #edf2f7;
      padding: 0.1rem 0.3rem;
      border-radius: 3px;
      font-size: 0.9em;
    }}
    footer {{
      margin-top: 3rem;
      padding-top: 1rem;
      border-top: 1px solid var(--border);
      font-size: 0.85rem;
      color: #888;
      text-align: center;
    }}
  </style>
</head>
<body>

{body}

  <footer>
    Generated by <strong>xsd-viewer</strong> &mdash;
    XSD schema visualization toolkit
  </footer>
</body>
</html>
"""


def main():
    args = parse_args()
    html_content = generate_html(args)
    output_path = args.output or f"{Path(args.schema_path).stem}_doc.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Documentation generated: {output_path}")


if __name__ == "__main__":
    main()
