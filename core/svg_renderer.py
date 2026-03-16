"""Orchestrator: XSD parsing -> layout -> SVG.

Main functions:
- render_element_diagram() — SVG for a specific element
- render_overview_diagram() — SVG for all top-level elements
- render_type_diagram() — SVG for a specific complexType
"""
from __future__ import annotations

import io
from typing import Optional

import svgwrite

from .xsd_model import XsdElement, XsdSchema
from .xsd_parser import SchemaRegistry, parse_schema_with_imports
from .layout_engine import (
    CONTAINER_HEADER_H,
    CONTAINER_PAD as LAYOUT_CONTAINER_PAD,
    ELEMENT_HEIGHT,
    LayoutNode,
    SubstitutionEntry,
    _merge_base_type,
    assign_positions,
    build_layout_tree,
    build_substitution_tree,
    compute_total_bounds,
    flatten_substitution_entries,
)
from .svg_primitives import (
    COLOR_ANNOTATION,
    COLOR_CONNECTOR,
    COLOR_ELEMENT_BORDER,
    COLOR_TYPE_BORDER,
    COMPOSITOR_HEIGHT,
    FONT_FAMILY,
    FONT_SIZE_ELEMENT,
    STROKE_WIDTH,
    _make_gradient_defs,
    draw_attribute_group,
    draw_compositor,
    draw_connector,
    draw_element_box,
    draw_horizontal_connector,
    draw_vertical_bus,
)

PADDING = 30
CONTAINER_PAD = LAYOUT_CONTAINER_PAD


def render_element_diagram(
    schema_path: str,
    element_name: str,
    depth: int = 2,
    *,
    registry: Optional[SchemaRegistry] = None,
    lang: str = "",
) -> str:
    schema, reg = _load_schema(schema_path, registry)

    element = schema.find_element(element_name)
    if element is None:
        for s in reg.all_schemas:
            element = s.find_element(element_name)
            if element:
                schema = s
                break
    if element is None:
        return _error_svg(f"Element '{element_name}' not found")

    root_node = build_layout_tree(element, schema, reg, depth=depth,
                                    diagram_namespace=element.namespace, lang=lang)
    assign_positions(root_node, x=PADDING, y=PADDING)

    total_w, total_h = compute_total_bounds(root_node)
    svg_w = total_w + PADDING * 2 + CONTAINER_PAD
    svg_h = total_h + PADDING * 2

    dwg = svgwrite.Drawing(size=(f"{svg_w}px", f"{svg_h}px"))
    dwg.viewbox(0, 0, svg_w, svg_h)
    _make_gradient_defs(dwg)

    _render_node(dwg, root_node)

    return dwg.tostring()


def render_overview_diagram(
    schema_path: str,
    *,
    registry: Optional[SchemaRegistry] = None,
    lang: str = "",
) -> str:
    schema, reg = _load_schema(schema_path, registry)

    elements = schema.elements
    if not elements:
        return _error_svg("No top-level elements found")

    nodes: list[LayoutNode] = []
    for elem in elements:
        node = build_layout_tree(elem, schema, reg, depth=0, lang=lang)
        nodes.append(node)

    y = PADDING
    max_w = 0.0
    for node in nodes:
        assign_positions(node, x=PADDING, y=y)
        y += node.subtree_height + 12
        w, _ = compute_total_bounds(node)
        max_w = max(max_w, w)

    svg_w = max_w + PADDING * 2
    svg_h = y + PADDING

    dwg = svgwrite.Drawing(size=(f"{svg_w}px", f"{svg_h}px"))
    dwg.viewbox(0, 0, svg_w, svg_h)
    _make_gradient_defs(dwg)

    for node in nodes:
        _render_node(dwg, node)

    return dwg.tostring()


def render_type_diagram(
    schema_path: str,
    type_name: str,
    depth: int = 2,
    *,
    registry: Optional[SchemaRegistry] = None,
    lang: str = "",
) -> str:
    schema, reg = _load_schema(schema_path, registry)

    ct = schema.find_complex_type(type_name)
    if ct is None:
        for s in reg.all_schemas:
            ct = s.find_complex_type(type_name)
            if ct:
                schema = s
                break
    if ct is None:
        return _error_svg(f"Type '{type_name}' not found")

    if ct.base_type and reg:
        ct = _merge_base_type(ct, reg, set())

    virtual_elem = XsdElement(
        name=type_name,
        namespace=schema.target_namespace,
        is_abstract=ct.is_abstract,
        annotation=ct.annotation,
    )
    if ct.content:
        virtual_elem.children = [ct.content]
    virtual_elem.attributes = list(ct.attributes)

    diagram_ns = schema.target_namespace

    root_node = build_layout_tree(virtual_elem, schema, reg, depth=depth,
                                    diagram_namespace=diagram_ns, lang=lang)

    subst_entries: list[SubstitutionEntry] = []
    if ct.is_abstract and reg:
        subst_entries = build_substitution_tree(
            type_name, schema.target_namespace, schema, reg,
            depth=depth, diagram_namespace=diagram_ns, lang=lang,
        )

    subst_flat = flatten_substitution_entries(subst_entries)

    assign_positions(root_node, x=PADDING, y=PADDING)
    total_w, total_h = compute_total_bounds(root_node)

    subst_indent = 30
    subst_gap = 25
    next_y = total_h + subst_gap
    for entry in subst_flat:
        assign_positions(entry.node, x=PADDING + subst_indent, y=next_y)
        ew, eh = compute_total_bounds(entry.node)
        total_w = max(total_w, ew)
        total_h = max(total_h, eh)
        next_y = eh + subst_gap

    svg_w = total_w + PADDING * 2
    svg_h = (next_y if subst_flat else total_h) + PADDING

    dwg = svgwrite.Drawing(size=(f"{svg_w}px", f"{svg_h}px"))
    dwg.viewbox(0, 0, svg_w, svg_h)
    _make_gradient_defs(dwg)

    _render_node(dwg, root_node)

    for entry in subst_flat:
        _render_node(dwg, entry.node)

    if subst_flat:
        _draw_inheritance_arrows(dwg, root_node, subst_flat)

    return dwg.tostring()


# --- Internal functions ---

def _load_schema(
    schema_path: str,
    registry: Optional[SchemaRegistry],
) -> tuple[XsdSchema, SchemaRegistry]:
    if registry:
        from .xsd_parser import XsdParser
        parser = XsdParser(registry)
        schema = parser.parse_file(schema_path)
        return schema, registry
    return parse_schema_with_imports(schema_path)


def _render_node(dwg: svgwrite.Drawing, node: LayoutNode) -> None:
    if node.kind == "element":
        if node.children:
            _draw_type_container_bg(dwg, node)

        g, _ = draw_element_box(
            dwg, node.display_name or node.name,
            is_required=node.is_required,
            is_ref=node.is_ref,
            is_abstract=node.is_abstract,
            has_text_content=node.has_text_content,
            has_children=node.has_children,
            is_expanded=bool(node.children),
            multiplicity=node.multiplicity,
            annotation=node.annotation,
            x=node.x,
            y=node.y,
        )
        dwg.add(g)

    elif node.kind == "compositor":
        g, _ = draw_compositor(
            dwg, node.compositor_kind,
            x=node.x,
            y=node.y,
            is_required=node.is_required,
            multiplicity=node.multiplicity,
        )
        dwg.add(g)

    elif node.kind == "attribute_group":
        g, _ = draw_attribute_group(
            dwg, node.attributes,
            is_expanded=True,
            x=node.x,
            y=node.y,
        )
        dwg.add(g)

    if node.children:
        _draw_connections(dwg, node)

    for child in node.children:
        _render_node(dwg, child)


def _draw_connections(dwg: svgwrite.Drawing, node: LayoutNode) -> None:
    parent_right_x = node.connect_x_right
    parent_cy = node.connect_y_center

    bus_x = (parent_right_x + node.children[0].x) / 2

    children_cy = [child.connect_y_center for child in node.children]
    all_cy = [parent_cy] + children_cy
    bus_top = min(all_cy)
    bus_bottom = max(all_cy)

    dwg.add(draw_horizontal_connector(
        dwg, parent_right_x, parent_cy, bus_x,
        is_required=True,
    ))

    if bus_top != bus_bottom:
        dwg.add(draw_vertical_bus(
            dwg, bus_x, bus_top, bus_bottom,
            is_required=True,
        ))

    for child in node.children:
        child_cy = child.connect_y_center
        child_left_x = child.x

        dwg.add(draw_horizontal_connector(
            dwg, bus_x, child_cy, child_left_x,
            is_required=child.is_required,
        ))


def _subtree_bounds(node: LayoutNode) -> tuple[float, float, float, float]:
    min_x = node.x
    min_y = node.y
    max_x = node.x + node.width
    max_y = node.y + node.height

    for child in node.children:
        cx1, cy1, cx2, cy2 = _subtree_bounds(child)
        min_x = min(min_x, cx1)
        min_y = min(min_y, cy1)
        max_x = max(max_x, cx2)
        max_y = max(max_y, cy2)

    if node.kind == "element" and node.children:
        pad = CONTAINER_PAD
        header_h = 18
        min_x = min(min_x, min_x - pad)
        min_y = min(min_y, min_y - pad - header_h)
        max_x = max_x + pad
        max_y = max_y + pad

    return min_x, min_y, max_x, max_y


def _draw_type_container_bg(dwg: svgwrite.Drawing, node: LayoutNode) -> None:
    all_min_x = float("inf")
    all_min_y = float("inf")
    all_max_x = float("-inf")
    all_max_y = float("-inf")
    for child in node.children:
        cx1, cy1, cx2, cy2 = _subtree_bounds(child)
        all_min_x = min(all_min_x, cx1)
        all_min_y = min(all_min_y, cy1)
        all_max_x = max(all_max_x, cx2)
        all_max_y = max(all_max_y, cy2)

    pad = CONTAINER_PAD
    header_h = 18

    container_x = all_min_x - pad
    container_y = all_min_y - pad - header_h
    container_w = (all_max_x - all_min_x) + pad * 2
    container_h = (all_max_y - all_min_y) + pad * 2 + header_h

    dwg.add(dwg.rect(
        insert=(container_x, container_y),
        size=(container_w, container_h),
        fill="#FFFFC0",
        stroke=COLOR_ELEMENT_BORDER,
        stroke_width=STROKE_WIDTH,
        stroke_dasharray="6,3",
        rx=4, ry=4,
    ))

    label = node.display_name or node.name
    dwg.add(dwg.text(label,
        insert=(container_x + pad, container_y + header_h - 4),
        font_size=FONT_SIZE_ELEMENT,
        font_family=FONT_FAMILY,
        fill=COLOR_ANNOTATION,
        font_style="italic",
    ))


def _draw_inheritance_arrows(
    dwg: svgwrite.Drawing,
    root_node: LayoutNode,
    subst_flat: list[SubstitutionEntry],
) -> None:
    node_map: dict[str, LayoutNode] = {root_node.name: root_node}
    for entry in subst_flat:
        node_map[entry.element.name] = entry.node

    arrow_sz = 5

    for entry in subst_flat:
        derived_node = entry.node
        base_node = node_map.get(entry.base_name)
        if not base_node:
            continue

        derived_cy = derived_node.connect_y_center
        derived_left = derived_node.x
        base_bottom = base_node.y + ELEMENT_HEIGHT

        if entry.base_name == root_node.name:
            vert_x = root_node.x + 5
        else:
            vert_x = base_node.x + 5

        points = [
            (derived_left, derived_cy),
            (vert_x, derived_cy),
            (vert_x, base_bottom + arrow_sz),
        ]
        dwg.add(dwg.polyline(
            points=points,
            stroke=COLOR_CONNECTOR,
            stroke_width=STROKE_WIDTH,
            fill="none",
        ))

        dwg.add(dwg.polygon(
            points=[
                (vert_x, base_bottom),
                (vert_x - arrow_sz / 2, base_bottom + arrow_sz),
                (vert_x + arrow_sz / 2, base_bottom + arrow_sz),
            ],
            fill=COLOR_CONNECTOR,
        ))


def _error_svg(message: str) -> str:
    dwg = svgwrite.Drawing(size=("400px", "60px"))
    dwg.viewbox(0, 0, 400, 60)
    dwg.add(dwg.rect(insert=(10, 10), size=(380, 40),
                      fill="#FEE", stroke="#C00", rx=4))
    dwg.add(dwg.text(message, insert=(20, 35),
                      font_size=12, font_family=FONT_FAMILY, fill="#C00"))
    return dwg.tostring()
