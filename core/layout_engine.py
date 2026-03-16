"""Tree auto-layout for XSD diagrams.

Algorithm:
1. Measure — recursive bounding box calculation for each node
2. Layout — assign (x,y) coordinates top-down, left-to-right
3. Connectors — generate lines between nodes

Horizontal layout (like XMLSpy): root on the left, children to the right.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .xsd_model import (
    CompositorKind,
    XsdAttribute,
    XsdComplexType,
    XsdCompositor,
    XsdElement,
    XsdSchema,
)
from .svg_primitives import (
    ATTR_HEIGHT,
    COMPOSITOR_WIDTH,
    COMPOSITOR_HEIGHT,
    ELEMENT_HEIGHT,
    ELEMENT_MIN_WIDTH,
    ELEMENT_PADDING_X,
    ELEMENT_ICON_SIZE,
    ELEMENT_ICON_MARGIN,
    ELEMENT_EXPAND_SIZE,
    CHAR_WIDTH,
    FONT_SIZE_ELEMENT,
    FONT_SIZE_ANNOTATION,
    ANNOTATION_CHAR_WIDTH,
    ANNOTATION_LINE_HEIGHT,
    ANNOTATION_MIN_WRAP_WIDTH,
    _text_width,
    _wrap_annotation,
    _annotation_height,
)

# --- Layout constants ---

H_GAP = 20
V_GAP = 8
ATTR_GAP = 4
COMPOSITOR_H_GAP = 15
CONTAINER_PAD = 14
CONTAINER_HEADER_H = 18


def _get_ns_prefix(namespace: str, registry=None) -> str:
    """Get short prefix for a namespace URI by looking up parsed schemas."""
    if registry:
        for schema in registry.all_schemas:
            p = schema.ns_prefix_map.get(namespace)
            if p:
                return p
    return ""


# --- Layout tree nodes ---

@dataclass
class LayoutNode:
    kind: str = "element"
    name: str = ""
    display_name: str = ""
    x: float = 0
    y: float = 0
    width: float = 0
    height: float = 0
    box_width: float = 0
    is_required: bool = True
    is_ref: bool = False
    is_abstract: bool = False
    has_text_content: bool = False
    has_children: bool = False
    multiplicity: str = ""
    compositor_kind: str = ""
    annotation: str = ""
    attributes: list[dict] = field(default_factory=list)
    children: list[LayoutNode] = field(default_factory=list)
    connect_x_right: float = 0
    connect_y_center: float = 0
    connect_x_left: float = 0
    subtree_height: float = 0


def _element_width(name: str, has_children: bool) -> float:
    text_w = _text_width(name)
    expand_space = ELEMENT_EXPAND_SIZE + 2 if has_children else 0
    return max(ELEMENT_MIN_WIDTH, text_w + expand_space + ELEMENT_PADDING_X * 2)


def _element_height(multiplicity: str, annotation: str, box_width: float = ELEMENT_MIN_WIDTH) -> float:
    h = ELEMENT_HEIGHT
    if multiplicity:
        h += 10
    if annotation:
        wrap_width = max(box_width, ANNOTATION_MIN_WRAP_WIDTH)
        ann_lines = _wrap_annotation(annotation, wrap_width)
        h += 2 + _annotation_height(ann_lines)
    return h


def _build_display_name(element: XsdElement, diagram_namespace: str = "", registry=None) -> str:
    """Build display name with namespace prefix.

    If element namespace matches diagram_namespace, no prefix is added.
    """
    ns = element.ref_namespace if element.is_ref and element.ref_namespace else element.namespace
    if ns == diagram_namespace:
        return element.name
    prefix = _get_ns_prefix(ns, registry)
    if prefix:
        return f"{prefix}:{element.name}"
    return element.name


def _find_all_substitution_members(element_name: str, namespace: str, registry) -> list:
    direct = registry.find_substitution_members(element_name, namespace)
    all_members = list(direct)
    for member in direct:
        sub = _find_all_substitution_members(member.name, member.namespace, registry)
        all_members.extend(sub)
    return all_members


def build_layout_tree(
    element: XsdElement,
    schema: XsdSchema,
    registry=None,
    depth: int = 2,
    _visited: Optional[set] = None,
    diagram_namespace: str = "",
    lang: str = "",
) -> LayoutNode:
    """Build layout tree from XsdElement.

    depth: expansion depth (0 = element only, 1 = element + children, ...)
    """
    if _visited is None:
        _visited = set()

    compositors = list(element.children)
    attrs = list(element.attributes)

    if not compositors and element.inline_type and element.inline_type.content:
        compositors = [element.inline_type.content]
        if not attrs and element.inline_type.attributes:
            attrs = list(element.inline_type.attributes)

    resolved_target = None
    if element.is_ref and not compositors and registry:
        ref_ns = element.ref_namespace or element.namespace
        target_schema = registry.get_by_namespace(ref_ns)
        if target_schema:
            resolved_target = target_schema.find_element(element.name)
            if resolved_target:
                if resolved_target.children:
                    compositors = list(resolved_target.children)
                elif resolved_target.inline_type and resolved_target.inline_type.content:
                    compositors = [resolved_target.inline_type.content]
                if not attrs and resolved_target.attributes:
                    attrs = list(resolved_target.attributes)

    resolved_ct = None
    resolve_elem = resolved_target or element
    if not compositors and resolve_elem.type_ref and registry:
        resolved_ct = _resolve_type(resolve_elem, schema if not resolved_target else (registry.get_by_namespace(resolve_elem.namespace) or schema), registry, set(_visited))
        if resolved_ct:
            if resolved_ct.content:
                compositors = [resolved_ct.content]
            if resolved_ct.attributes and not attrs:
                attrs = list(resolved_ct.attributes)

    has_children = bool(compositors) or bool(attrs)

    ann_text = ""
    if element.annotation and element.annotation.has_content():
        ann_text = element.annotation.get_doc(lang)
    elif resolved_target and resolved_target.annotation and resolved_target.annotation.has_content():
        ann_text = resolved_target.annotation.get_doc(lang)
    elif resolved_ct and resolved_ct.annotation and resolved_ct.annotation.has_content():
        ann_text = resolved_ct.annotation.get_doc(lang)
    elif element.inline_type and element.inline_type.annotation and element.inline_type.annotation.has_content():
        ann_text = element.inline_type.annotation.get_doc(lang)

    display_name = _build_display_name(element, diagram_namespace, registry)

    node = LayoutNode(
        kind="element",
        name=element.name,
        display_name=display_name,
        is_required=element.is_required,
        is_ref=element.is_ref,
        is_abstract=element.is_abstract,
        has_text_content=element.has_text_content,
        has_children=has_children,
        multiplicity=element.multiplicity_label,
        annotation=ann_text,
    )
    box_w = _element_width(display_name, has_children)
    node.box_width = box_w
    node.width = box_w
    node.height = _element_height(element.multiplicity_label, ann_text, box_w)

    if ann_text:
        wrap_width = max(box_w, ANNOTATION_MIN_WRAP_WIDTH)
        ann_lines = _wrap_annotation(ann_text, wrap_width)
        max_line_w = max(len(ln) for ln in ann_lines) * ANNOTATION_CHAR_WIDTH + 4
        node.width = max(node.width, max_line_w)

    if depth <= 0:
        node.subtree_height = node.height
        return node

    if not has_children:
        node.subtree_height = node.height
        return node

    for comp in compositors:
        comp_node = _build_compositor_node(comp, schema, registry, depth - 1, _visited, diagram_namespace, lang=lang)
        node.children.append(comp_node)

    if attrs:
        attr_node = LayoutNode(
            kind="attribute_group",
            name="attributes",
            attributes=[
                {"name": a.name, "is_required": a.use.value == "required"}
                for a in attrs
            ],
        )
        attr_h = ATTR_HEIGHT + len(attrs) * (ATTR_HEIGHT + 2) + 2
        # Calculate real width matching draw_attribute_group rendering
        from .svg_primitives import ATTR_PADDING_X, ATTR_ICON_SIZE, FONT_SIZE_ATTR
        max_name_w = max((_text_width(a.name, FONT_SIZE_ATTR) for a in attrs), default=40)
        attr_node.width = max(90, ATTR_PADDING_X + ATTR_ICON_SIZE + 4 + max_name_w + ATTR_PADDING_X * 2)
        attr_node.height = attr_h
        attr_node.subtree_height = attr_h
        node.children.append(attr_node)

    _compute_subtree_height(node)
    return node


def _build_compositor_node(
    compositor: XsdCompositor,
    schema: XsdSchema,
    registry,
    depth: int,
    visited: set,
    diagram_namespace: str = "",
    lang: str = "",
) -> LayoutNode:
    comp_node = LayoutNode(
        kind="compositor",
        compositor_kind=compositor.kind.value,
        is_required=compositor.is_required,
        multiplicity=compositor.multiplicity_label,
    )
    comp_node.width = COMPOSITOR_WIDTH
    comp_node.height = COMPOSITOR_HEIGHT

    for elem in compositor.elements:
        child = build_layout_tree(elem, schema, registry, depth, visited, diagram_namespace=diagram_namespace, lang=lang)
        comp_node.children.append(child)

    for sub_comp in compositor.compositors:
        sub_node = _build_compositor_node(sub_comp, schema, registry, depth, visited, diagram_namespace, lang=lang)
        comp_node.children.append(sub_node)

    _compute_subtree_height(comp_node)
    return comp_node


def _merge_base_type(
    ct: XsdComplexType,
    registry,
    visited: set,
) -> XsdComplexType:
    """Merge base type elements (xs:extension base=...) with extension.

    Base elements are inserted BEFORE extension elements — like in XMLSpy.
    Returns a new XsdComplexType (does not mutate the original).
    """
    if not ct.base_type or not registry:
        return ct

    base_key = f"{ct.base_namespace}:{ct.base_type}"
    if base_key in visited:
        return ct
    visited.add(base_key)

    base_schema = registry.get_by_namespace(ct.base_namespace)
    if not base_schema:
        return ct
    base_local = ct.base_type.split(":", 1)[-1] if ":" in ct.base_type else ct.base_type
    base_ct = base_schema.find_complex_type(base_local)
    if not base_ct:
        return ct

    if base_ct.base_type:
        base_ct = _merge_base_type(base_ct, registry, visited)

    merged_content = ct.content
    if base_ct.content:
        if ct.content:
            merged_content = XsdCompositor(
                kind=ct.content.kind,
                min_occurs=ct.content.min_occurs,
                max_occurs=ct.content.max_occurs,
                elements=list(base_ct.content.elements) + list(ct.content.elements),
                compositors=list(base_ct.content.compositors) + list(ct.content.compositors),
            )
        else:
            merged_content = base_ct.content

    merged_attrs = list(base_ct.attributes) + list(ct.attributes) if base_ct.attributes else list(ct.attributes)

    return XsdComplexType(
        name=ct.name,
        namespace=ct.namespace,
        base_type=ct.base_type,
        base_namespace=ct.base_namespace,
        is_abstract=ct.is_abstract,
        is_mixed=ct.is_mixed,
        annotation=ct.annotation,
        content=merged_content,
        attributes=merged_attrs,
    )


def _resolve_type(
    element: XsdElement,
    schema: XsdSchema,
    registry,
    visited: set,
) -> Optional[XsdComplexType]:
    type_ref = element.type_ref
    if not type_ref:
        return None

    if ":" in type_ref:
        prefix, local = type_ref.split(":", 1)
    else:
        prefix, local = "", type_ref

    type_key = f"{element.type_namespace}:{local}"
    if type_key in visited:
        return None
    visited.add(type_key)

    ct = None
    if element.type_namespace and registry:
        target_schema = registry.get_by_namespace(element.type_namespace)
        if target_schema:
            ct = target_schema.find_complex_type(local)

    if ct is None:
        ct = schema.find_complex_type(local)

    if ct and ct.base_type and registry:
        ct = _merge_base_type(ct, registry, set(visited))

    return ct


def _compute_subtree_height(node: LayoutNode) -> None:
    if not node.children:
        node.subtree_height = node.height
        return

    total = 0
    for i, child in enumerate(node.children):
        if child.subtree_height == 0:
            _compute_subtree_height(child)
        total += child.subtree_height
        if i < len(node.children) - 1:
            total += V_GAP

    if node.kind == "element":
        total += CONTAINER_PAD * 2 + CONTAINER_HEADER_H

    node.subtree_height = max(node.height, total)


# --- Position assignment ---

def assign_positions(node: LayoutNode, x: float = 0, y: float = 0) -> None:
    node.x = x
    node.y = y + (node.subtree_height - node.height) / 2

    node.connect_x_right = node.x + (node.box_width if node.box_width else node.width)
    node.connect_x_left = node.x
    if node.kind == "element":
        node.connect_y_center = node.y + ELEMENT_HEIGHT / 2
    else:
        node.connect_y_center = node.y + node.height / 2

    if not node.children:
        return

    child_x = node.x + node.width + H_GAP
    if node.kind == "compositor":
        child_x = node.x + node.width + COMPOSITOR_H_GAP

    child_y = y
    if node.kind == "element":
        child_y += CONTAINER_PAD + CONTAINER_HEADER_H
    for child in node.children:
        assign_positions(child, child_x, child_y)
        child_y += child.subtree_height + V_GAP


def compute_total_bounds(node: LayoutNode) -> tuple[float, float]:
    max_x = node.x + node.width
    max_y = node.y + node.height

    if node.multiplicity:
        max_x = max(max_x, node.x + node.width + 30)

    for child in node.children:
        cx, cy = compute_total_bounds(child)
        max_x = max(max_x, cx)
        max_y = max(max_y, cy)

    return max_x, max_y


# --- Substitution group (inheritance) ---

@dataclass
class SubstitutionEntry:
    element: XsdElement
    node: LayoutNode
    base_name: str
    base_namespace: str
    children: list[SubstitutionEntry] = field(default_factory=list)


def build_substitution_tree(
    base_element_name: str,
    base_namespace: str,
    schema: XsdSchema,
    registry,
    depth: int = 1,
    diagram_namespace: str = "",
    lang: str = "",
) -> list[SubstitutionEntry]:
    if not registry:
        return []
    direct = registry.find_substitution_members(base_element_name, base_namespace)
    entries: list[SubstitutionEntry] = []
    for member in direct:
        member_node = build_layout_tree(
            member, schema, registry, depth=depth,
            diagram_namespace=diagram_namespace, lang=lang,
        )
        sub_entries = build_substitution_tree(
            member.name, member.namespace, schema, registry, depth, diagram_namespace, lang=lang,
        )
        entries.append(SubstitutionEntry(
            element=member, node=member_node,
            base_name=base_element_name, base_namespace=base_namespace,
            children=sub_entries,
        ))
    return entries


def flatten_substitution_entries(entries: list[SubstitutionEntry]) -> list[SubstitutionEntry]:
    result: list[SubstitutionEntry] = []
    for entry in entries:
        result.append(entry)
        result.extend(flatten_substitution_entries(entry.children))
    return result
