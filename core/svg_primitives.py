"""SVG primitives for XSD diagrams in Altova XMLSpy notation.

Each function creates an SVG group (<g>) and returns (group, width, height).
Uses the svgwrite library.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import svgwrite
from svgwrite.container import Group

# --- Constants ---

ELEMENT_HEIGHT = 26
ELEMENT_MIN_WIDTH = 120
ELEMENT_PADDING_X = 10
ELEMENT_ICON_SIZE = 14
ELEMENT_ICON_MARGIN = 4
ELEMENT_EXPAND_SIZE = 14
ELEMENT_CORNER_RADIUS = 3

ATTR_HEIGHT = 20
ATTR_MIN_WIDTH = 80
ATTR_ICON_SIZE = 10
ATTR_PADDING_X = 6

COMPOSITOR_WIDTH = 32
COMPOSITOR_HEIGHT = 18

FONT_FAMILY = "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif"
FONT_SIZE_ELEMENT = 11
FONT_SIZE_ATTR = 9
FONT_SIZE_MULTIPLICITY = 8
FONT_SIZE_ICON = 9
FONT_SIZE_ANNOTATION = 10

CHAR_WIDTH = 6.6
ANNOTATION_CHAR_WIDTH = 6.0
ANNOTATION_LINE_HEIGHT = 13
ANNOTATION_MIN_WRAP_WIDTH = 250

SHADOW_DX = 3
SHADOW_DY = 3
SHADOW_COLOR = "#CCCCCC"

COLOR_ELEMENT_BG = "#FFFFCC"
COLOR_ELEMENT_BORDER = "#999966"
COLOR_ELEMENT_ICON_BG = "#999966"
COLOR_REF_ICON_BG = "#4CAF50"
COLOR_ABSTRACT_ICON_BG = "#CC9933"
COLOR_ATTR_BG = "#F0F0E0"
COLOR_ATTR_BORDER = "#999966"
COLOR_ATTR_ICON_BG = "#999966"
COLOR_TYPE_BG = "#FFFFF0"
COLOR_TYPE_BORDER = "#CC9933"
COLOR_TEXT = "#333333"
COLOR_TEXT_LIGHT = "#888888"
COLOR_NS_PREFIX = "#666666"
COLOR_ANNOTATION = "#666666"
COLOR_CONNECTOR = "#666666"
COLOR_CONNECTOR_OPT = "#999999"
COLOR_WHITE = "#FFFFFF"
COLOR_COMPOSITOR_BG = "#FFFFFF"
COLOR_COMPOSITOR_BORDER = "#666666"

STROKE_WIDTH = 1.2
STROKE_DASH = "5,3"


@dataclass
class BBox:
    width: float
    height: float


# --- Utilities ---

def _text_width(text: str, font_size: float = FONT_SIZE_ELEMENT) -> float:
    return len(text) * CHAR_WIDTH * (font_size / FONT_SIZE_ELEMENT)


def _wrap_annotation(text: str, max_width_px: float) -> list[str]:
    max_chars = max(10, int(max_width_px / ANNOTATION_CHAR_WIDTH))
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = f"{current} {word}" if current else word
        if len(test) <= max_chars:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines if lines else [""]


def _annotation_height(lines: list[str]) -> float:
    return len(lines) * ANNOTATION_LINE_HEIGHT + 4


def _make_gradient_defs(dwg: svgwrite.Drawing) -> None:
    grad_el = dwg.linearGradient(id="gradElement", x1="0%", y1="0%", x2="0%", y2="100%")
    grad_el.add_stop_color(0, "#FFFFF0")
    grad_el.add_stop_color(1, "#FFFFCC")
    dwg.defs.add(grad_el)

    grad_type = dwg.linearGradient(id="gradType", x1="0%", y1="0%", x2="0%", y2="100%")
    grad_type.add_stop_color(0, "#FFFFF5")
    grad_type.add_stop_color(1, "#FFFDE0")
    dwg.defs.add(grad_type)

    grad_attr = dwg.linearGradient(id="gradAttr", x1="0%", y1="0%", x2="0%", y2="100%")
    grad_attr.add_stop_color(0, "#F8F8E8")
    grad_attr.add_stop_color(1, "#F0F0D8")
    dwg.defs.add(grad_attr)


# --- Primitives ---

def draw_element_box(
    dwg: svgwrite.Drawing,
    name: str,
    *,
    is_required: bool = True,
    is_ref: bool = False,
    is_abstract: bool = False,
    has_text_content: bool = False,
    has_children: bool = False,
    is_expanded: bool = False,
    multiplicity: str = "",
    annotation: str = "",
    x: float = 0,
    y: float = 0,
) -> tuple[Group, BBox]:
    text_w = _text_width(name)
    expand_space = ELEMENT_EXPAND_SIZE + 2 if has_children else 0
    total_w = max(ELEMENT_MIN_WIDTH, text_w + expand_space + ELEMENT_PADDING_X * 2)

    g = dwg.g(transform=f"translate({x},{y})")

    g.add(dwg.rect(
        insert=(SHADOW_DX, SHADOW_DY),
        size=(total_w, ELEMENT_HEIGHT),
        fill=SHADOW_COLOR, stroke="none",
        rx=ELEMENT_CORNER_RADIUS, ry=ELEMENT_CORNER_RADIUS,
    ))

    bg_fill = COLOR_WHITE
    stroke_args = {
        "stroke": COLOR_ELEMENT_BORDER,
        "stroke_width": STROKE_WIDTH,
        "fill": bg_fill,
        "rx": ELEMENT_CORNER_RADIUS,
        "ry": ELEMENT_CORNER_RADIUS,
    }
    if not is_required:
        stroke_args["stroke_dasharray"] = STROKE_DASH

    g.add(dwg.rect(insert=(0, 0), size=(total_w, ELEMENT_HEIGHT), **stroke_args))

    icon_sz = round(ELEMENT_HEIGHT * 0.2)
    if not is_expanded and is_ref:
        arr_sz = round(icon_sz * 0.67)
        ax = 2
        ay = ELEMENT_HEIGHT - 2
        tip_x = ax + arr_sz + 2
        tip_y = ay - arr_sz - 2
        g.add(dwg.line(
            start=(ax, ay), end=(tip_x - 1.5, tip_y + 1.5),
            stroke=COLOR_TEXT, stroke_width=1.8,
        ))
        g.add(dwg.polygon(
            points=[(tip_x, tip_y), (tip_x - 3.5, tip_y + 0.5), (tip_x - 0.5, tip_y + 3.5)],
            fill=COLOR_TEXT,
        ))
    elif not is_expanded:
        for dy in range(3):
            line_y = 3 + dy * 2.5
            g.add(dwg.line(
                start=(3, line_y), end=(3 + icon_sz, line_y),
                stroke=COLOR_TEXT, stroke_width=0.8,
            ))

    text_x = ELEMENT_PADDING_X
    text_y = ELEMENT_HEIGHT / 2 + 4
    g.add(dwg.text(name,
        insert=(text_x, text_y),
        font_size=FONT_SIZE_ELEMENT, font_family=FONT_FAMILY,
        fill=COLOR_TEXT, font_weight="bold",
    ))

    if has_children:
        btn_x = total_w - ELEMENT_EXPAND_SIZE - 2
        btn_y = (ELEMENT_HEIGHT - ELEMENT_EXPAND_SIZE) / 2
        g.add(dwg.rect(
            insert=(btn_x, btn_y), size=(ELEMENT_EXPAND_SIZE, ELEMENT_EXPAND_SIZE),
            fill=COLOR_WHITE, stroke=COLOR_ELEMENT_BORDER, stroke_width=0.8, rx=2, ry=2,
        ))
        cx = btn_x + ELEMENT_EXPAND_SIZE / 2
        cy = btn_y + ELEMENT_EXPAND_SIZE / 2
        g.add(dwg.line(
            start=(cx - 3, cy), end=(cx + 3, cy),
            stroke=COLOR_ELEMENT_BORDER, stroke_width=1,
        ))
        if not is_expanded:
            g.add(dwg.line(
                start=(cx, cy - 3), end=(cx, cy + 3),
                stroke=COLOR_ELEMENT_BORDER, stroke_width=1,
            ))

    total_h = ELEMENT_HEIGHT
    if multiplicity:
        mult_x = total_w + 2
        mult_y = ELEMENT_HEIGHT + 1
        g.add(dwg.text(multiplicity,
            insert=(mult_x, mult_y),
            font_size=FONT_SIZE_MULTIPLICITY, font_family=FONT_FAMILY,
            fill=COLOR_TEXT_LIGHT, font_style="italic",
        ))
        total_h = ELEMENT_HEIGHT + 10

    if annotation:
        wrap_width = max(total_w, ANNOTATION_MIN_WRAP_WIDTH)
        ann_lines = _wrap_annotation(annotation, wrap_width)
        ann_y = total_h + 2
        for i, line in enumerate(ann_lines):
            g.add(dwg.text(line,
                insert=(2, ann_y + FONT_SIZE_ANNOTATION + i * ANNOTATION_LINE_HEIGHT),
                font_size=FONT_SIZE_ANNOTATION, font_family=FONT_FAMILY,
                fill=COLOR_ANNOTATION, font_style="italic",
            ))
        max_line_w = max(len(ln) for ln in ann_lines) * ANNOTATION_CHAR_WIDTH
        total_w = max(total_w, max_line_w + 4)
        total_h = ann_y + _annotation_height(ann_lines)

    return g, BBox(width=total_w, height=total_h)


def draw_compositor(
    dwg: svgwrite.Drawing,
    kind: str,
    *,
    x: float = 0,
    y: float = 0,
    is_required: bool = True,
    multiplicity: str = "",
) -> tuple[Group, BBox]:
    w = COMPOSITOR_WIDTH
    h = COMPOSITOR_HEIGHT
    rx = h / 2
    g = dwg.g(transform=f"translate({x},{y})")

    stroke_args = {
        "stroke": COLOR_COMPOSITOR_BORDER,
        "stroke_width": STROKE_WIDTH,
        "fill": COLOR_COMPOSITOR_BG,
        "rx": rx, "ry": rx,
    }
    if not is_required:
        stroke_args["stroke_dasharray"] = STROKE_DASH

    g.add(dwg.rect(insert=(0, 0), size=(w, h), **stroke_args))

    cx = w / 2
    cy = h / 2

    if kind == "sequence":
        g.add(dwg.line(
            start=(cx - 10, cy), end=(cx + 10, cy),
            stroke=COLOR_COMPOSITOR_BORDER, stroke_width=1.0,
        ))
        for dx in [-6, 0, 6]:
            g.add(dwg.circle(center=(cx + dx, cy), r=2.0, fill=COLOR_COMPOSITOR_BORDER))
    elif kind == "choice":
        icon_color = "#333333"
        sq = 3.2
        for dy_frac in [-0.22, 0, 0.22]:
            g.add(dwg.rect(
                insert=(cx - sq / 2, cy + h * dy_frac - sq / 2),
                size=(sq, sq), fill=icon_color,
            ))
        sw_x = w * 0.15
        g.add(dwg.line(start=(sw_x, cy), end=(sw_x + 4, cy), stroke=icon_color, stroke_width=1.0))
        g.add(dwg.line(start=(sw_x + 4, cy), end=(sw_x + 8, cy - 3), stroke=icon_color, stroke_width=1.0))
        ev_xr = w * 0.82
        for dy_frac in [-0.22, 0, 0.22]:
            g.add(dwg.line(
                start=(cx + sq / 2 + 1, cy + h * dy_frac),
                end=(ev_xr, cy + h * dy_frac),
                stroke=icon_color, stroke_width=1.0,
            ))
        g.add(dwg.line(start=(ev_xr, cy - h * 0.22), end=(ev_xr, cy + h * 0.22), stroke=icon_color, stroke_width=1.0))
        g.add(dwg.line(start=(ev_xr, cy), end=(w * 0.9, cy), stroke=icon_color, stroke_width=1.0))
    elif kind == "all":
        for dx in [-4, 0, 4]:
            g.add(dwg.circle(center=(cx + dx, cy), r=1.5, fill=COLOR_COMPOSITOR_BORDER))

    total_h = h
    if multiplicity:
        g.add(dwg.text(multiplicity,
            insert=(w + 1, h + 1),
            font_size=FONT_SIZE_MULTIPLICITY, font_family=FONT_FAMILY,
            fill=COLOR_TEXT_LIGHT, font_style="italic",
        ))
        total_h = h + 10

    return g, BBox(width=w, height=total_h)


def draw_attribute_group(
    dwg: svgwrite.Drawing,
    attributes: list[dict],
    *,
    is_expanded: bool = True,
    x: float = 0,
    y: float = 0,
) -> tuple[Group, BBox]:
    g = dwg.g(transform=f"translate({x},{y})")

    if not is_expanded or not attributes:
        w = 90
        h = ATTR_HEIGHT
        g.add(dwg.rect(
            insert=(0, 0), size=(w, h),
            fill=COLOR_ATTR_BG, stroke=COLOR_ATTR_BORDER, stroke_width=1, rx=2, ry=2,
        ))
        g.add(dwg.rect(
            insert=(3, 4), size=(12, 12),
            fill=COLOR_WHITE, stroke=COLOR_ATTR_BORDER, stroke_width=0.8, rx=1, ry=1,
        ))
        g.add(dwg.line(start=(6, 10), end=(12, 10), stroke=COLOR_ATTR_BORDER, stroke_width=1))
        g.add(dwg.line(start=(9, 7), end=(9, 13), stroke=COLOR_ATTR_BORDER, stroke_width=1))
        g.add(dwg.text("attributes",
            insert=(18, h / 2 + 3),
            font_size=FONT_SIZE_ATTR, font_family=FONT_FAMILY,
            fill=COLOR_TEXT, font_style="italic",
        ))
        return g, BBox(width=w, height=h)

    max_name_w = max(_text_width(a["name"], FONT_SIZE_ATTR) for a in attributes) if attributes else 40
    w = max(90, ATTR_PADDING_X + ATTR_ICON_SIZE + 4 + max_name_w + ATTR_PADDING_X * 2)
    header_h = ATTR_HEIGHT
    total_h = header_h + len(attributes) * (ATTR_HEIGHT + 2) + 2

    g.add(dwg.rect(
        insert=(0, 0), size=(w, total_h),
        fill=COLOR_ATTR_BG, stroke=COLOR_ATTR_BORDER, stroke_width=1, rx=2, ry=2,
    ))
    g.add(dwg.rect(
        insert=(3, 4), size=(12, 12),
        fill=COLOR_WHITE, stroke=COLOR_ATTR_BORDER, stroke_width=0.8, rx=1, ry=1,
    ))
    g.add(dwg.line(start=(6, 10), end=(12, 10), stroke=COLOR_ATTR_BORDER, stroke_width=1))
    g.add(dwg.text("attributes",
        insert=(18, header_h / 2 + 3),
        font_size=FONT_SIZE_ATTR, font_family=FONT_FAMILY,
        fill=COLOR_TEXT, font_style="italic",
    ))
    g.add(dwg.line(
        start=(0, header_h), end=(w, header_h),
        stroke=COLOR_ATTR_BORDER, stroke_width=0.5,
    ))

    ay = header_h + 2
    for attr in attributes:
        is_req = attr.get("is_required", False)
        g.add(dwg.rect(
            insert=(ATTR_PADDING_X, ay + (ATTR_HEIGHT - ATTR_ICON_SIZE) / 2),
            size=(ATTR_ICON_SIZE, ATTR_ICON_SIZE),
            fill=COLOR_ATTR_ICON_BG, rx=1, ry=1,
        ))
        text_x = ATTR_PADDING_X + ATTR_ICON_SIZE + 4
        if not is_req:
            g.add(dwg.line(
                start=(text_x, ay + ATTR_HEIGHT - 4),
                end=(text_x + _text_width(attr["name"], FONT_SIZE_ATTR), ay + ATTR_HEIGHT - 4),
                stroke=COLOR_ATTR_BORDER, stroke_width=0.5, stroke_dasharray="2,2",
            ))
        g.add(dwg.text(attr["name"],
            insert=(text_x, ay + ATTR_HEIGHT / 2 + 3),
            font_size=FONT_SIZE_ATTR, font_family=FONT_FAMILY,
            fill=COLOR_TEXT, font_weight="bold" if is_req else "normal",
        ))
        ay += ATTR_HEIGHT + 2

    return g, BBox(width=w, height=total_h)


def draw_type_container(
    dwg: svgwrite.Drawing,
    name: str,
    namespace_prefix: str = "",
    *,
    x: float = 0,
    y: float = 0,
    inner_width: float = 200,
    inner_height: float = 100,
    annotation: str = "",
) -> tuple[Group, BBox]:
    padding = 10
    header_h = 22
    ann_h = 0
    if annotation:
        ann_h = FONT_SIZE_ANNOTATION + 4
    total_w = inner_width + padding * 2
    total_h = inner_height + header_h + ann_h + padding * 2

    g = dwg.g(transform=f"translate({x},{y})")

    g.add(dwg.rect(
        insert=(0, 0), size=(total_w, total_h),
        fill="url(#gradType)", stroke=COLOR_TYPE_BORDER,
        stroke_width=STROKE_WIDTH, stroke_dasharray="6,3", rx=4, ry=4,
    ))

    label = name
    if namespace_prefix:
        label = f"{namespace_prefix}:{name}"
    g.add(dwg.text(label,
        insert=(padding, header_h - 6),
        font_size=FONT_SIZE_ELEMENT, font_family=FONT_FAMILY,
        fill=COLOR_TYPE_BORDER, font_weight="bold", font_style="italic",
    ))

    if annotation:
        ann_lines = _wrap_annotation(annotation, inner_width)
        for i, line in enumerate(ann_lines):
            g.add(dwg.text(line,
                insert=(padding, header_h - 6 + FONT_SIZE_ANNOTATION + 2 + i * ANNOTATION_LINE_HEIGHT),
                font_size=FONT_SIZE_ANNOTATION, font_family=FONT_FAMILY,
                fill=COLOR_ANNOTATION, font_style="italic",
            ))

    sep_y = header_h + ann_h
    g.add(dwg.line(
        start=(0, sep_y), end=(total_w, sep_y),
        stroke=COLOR_TYPE_BORDER, stroke_width=0.5, stroke_dasharray="4,2",
    ))

    return g, BBox(width=total_w, height=total_h)


def draw_connector(
    dwg: svgwrite.Drawing,
    x1: float, y1: float,
    x2: float, y2: float,
    *,
    is_required: bool = True,
) -> svgwrite.shapes.Line:
    args = {
        "stroke": COLOR_CONNECTOR if is_required else COLOR_CONNECTOR_OPT,
        "stroke_width": STROKE_WIDTH,
    }
    if not is_required:
        args["stroke_dasharray"] = STROKE_DASH
    return dwg.line(start=(x1, y1), end=(x2, y2), **args)


def draw_horizontal_connector(
    dwg: svgwrite.Drawing,
    x1: float, y: float,
    x2: float,
    *,
    is_required: bool = True,
) -> svgwrite.shapes.Line:
    return draw_connector(dwg, x1, y, x2, y, is_required=is_required)


def draw_vertical_bus(
    dwg: svgwrite.Drawing,
    x: float,
    y_top: float,
    y_bottom: float,
    *,
    is_required: bool = True,
) -> svgwrite.shapes.Line:
    return draw_connector(dwg, x, y_top, x, y_bottom, is_required=is_required)
