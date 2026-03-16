"""XSD schema parser using lxml -> XsdSchema model.

Supports:
- xs:element (local and global, ref references)
- xs:complexType (sequence, choice, all, extension, restriction)
- xs:simpleType (restriction with enumeration)
- xs:attribute
- xs:import (cross-schema resolution)
- xs:annotation/xs:documentation
- anonymous inline complexType
- abstract types and substitutionGroup
"""
from __future__ import annotations

import os
from typing import Optional

from lxml import etree

from .xsd_model import (
    AttributeUse,
    CompositorKind,
    XsdAnnotation,
    XsdAttribute,
    XsdComplexType,
    XsdCompositor,
    XsdElement,
    XsdImport,
    XsdSchema,
    XsdSimpleType,
)

XS = "http://www.w3.org/2001/XMLSchema"
XS_PREFIX = f"{{{XS}}}"

_XS_TEXT_TYPES = {
    "xs:string", "xs:normalizedString", "xs:token",
    "xs:NMTOKEN", "xs:Name", "xs:NCName",
    "xs:integer", "xs:int", "xs:long", "xs:short", "xs:byte",
    "xs:decimal", "xs:float", "xs:double",
    "xs:boolean", "xs:dateTime", "xs:date", "xs:time",
    "xs:hexBinary", "xs:base64Binary",
    "xs:anyURI", "xs:ID", "xs:IDREF",
    "xs:anyType",
}


class SchemaRegistry:
    """Registry of parsed schemas — avoids repeated parsing."""

    def __init__(self) -> None:
        self._by_namespace: dict[str, XsdSchema] = {}
        self._by_path: dict[str, XsdSchema] = {}

    def get_by_namespace(self, ns: str) -> Optional[XsdSchema]:
        return self._by_namespace.get(ns)

    def get_by_path(self, path: str) -> Optional[XsdSchema]:
        return self._by_path.get(os.path.normpath(path))

    def register(self, schema: XsdSchema) -> None:
        if schema.target_namespace:
            self._by_namespace[schema.target_namespace] = schema
        if schema.schema_location:
            self._by_path[os.path.normpath(schema.schema_location)] = schema

    @property
    def all_schemas(self) -> list[XsdSchema]:
        seen = set()
        result = []
        for s in self._by_namespace.values():
            key = id(s)
            if key not in seen:
                seen.add(key)
                result.append(s)
        return result

    def find_substitution_members(self, element_name: str, namespace: str) -> list:
        members = []
        for schema in self.all_schemas:
            for elem in schema.elements:
                if elem.substitution_group == element_name and elem.substitution_group_namespace == namespace:
                    members.append(elem)
        return members


class XsdParser:

    def __init__(self, registry: Optional[SchemaRegistry] = None) -> None:
        self.registry = registry or SchemaRegistry()

    def _is_simple_type(self, type_ref: str, type_namespace: str) -> bool:
        _, local = self._split_qname(type_ref)
        target_schema = self.registry.get_by_namespace(type_namespace)
        if target_schema:
            for st in target_schema.simple_types:
                if st.name == local:
                    return True
        return False

    def parse_file(self, schema_path: str) -> XsdSchema:
        abs_path = os.path.abspath(schema_path)

        cached = self.registry.get_by_path(abs_path)
        if cached is not None:
            return cached

        tree = etree.parse(abs_path)
        root = tree.getroot()
        return self._parse_schema_element(root, abs_path)

    def _parse_schema_element(self, root: etree._Element, abs_path: str) -> XsdSchema:
        schema = XsdSchema(
            target_namespace=root.get("targetNamespace", ""),
            schema_location=abs_path,
            version=root.get("version", ""),
        )
        self.registry.register(schema)

        ns_map = self._build_ns_map(root)

        # Populate dynamic namespace URI -> prefix map
        schema.ns_prefix_map = {uri: prefix for prefix, uri in ns_map.items() if prefix}

        # Schema annotation
        for child in root:
            tag = self._local_tag(child)
            if tag == "annotation":
                schema.annotation = self._parse_annotation(child)
                break

        # Imports
        base_dir = os.path.dirname(abs_path)
        for child in root:
            tag = self._local_tag(child)
            if tag == "import":
                imp = XsdImport(
                    namespace=child.get("namespace", ""),
                    schema_location=child.get("schemaLocation", ""),
                )
                schema.imports.append(imp)
                if imp.schema_location:
                    imp_path = os.path.join(base_dir, imp.schema_location)
                    if os.path.isfile(imp_path):
                        self.parse_file(imp_path)

        # Global elements, complexType, simpleType
        for child in root:
            tag = self._local_tag(child)
            if tag == "element":
                elem = self._parse_element(child, schema.target_namespace, ns_map)
                schema.elements.append(elem)
            elif tag == "complexType":
                ct = self._parse_complex_type(child, schema.target_namespace, ns_map)
                schema.complex_types.append(ct)
            elif tag == "simpleType":
                st = self._parse_simple_type(child, schema.target_namespace)
                schema.simple_types.append(st)

        return schema

    # --- Element parsing ---

    def _parse_element(
        self,
        el: etree._Element,
        target_ns: str,
        ns_map: dict[str, str],
    ) -> XsdElement:
        elem = XsdElement(namespace=target_ns)

        ref = el.get("ref")
        if ref:
            elem.is_ref = True
            prefix, local = self._split_qname(ref)
            elem.name = local
            elem.ref_namespace = ns_map.get(prefix, target_ns) if prefix else target_ns
        else:
            elem.name = el.get("name", "")

        type_ref = el.get("type", "")
        if type_ref:
            elem.type_ref = type_ref
            prefix, _ = self._split_qname(type_ref)
            elem.type_namespace = ns_map.get(prefix, "") if prefix else target_ns
            if type_ref in _XS_TEXT_TYPES or type_ref.startswith("xs:"):
                elem.has_text_content = True
            elif not elem.has_text_content and elem.type_namespace:
                if self._is_simple_type(type_ref, elem.type_namespace):
                    elem.has_text_content = True

        elem.is_abstract = el.get("abstract", "false").lower() == "true"

        subst_group = el.get("substitutionGroup", "")
        if subst_group:
            if ":" in subst_group:
                sg_prefix, sg_local = subst_group.split(":", 1)
                elem.substitution_group = sg_local
                elem.substitution_group_namespace = ns_map.get(sg_prefix, target_ns)
            else:
                elem.substitution_group = subst_group
                elem.substitution_group_namespace = target_ns

        elem.min_occurs = int(el.get("minOccurs", "1"))
        max_str = el.get("maxOccurs", "1")
        elem.max_occurs = -1 if max_str == "unbounded" else int(max_str)

        for child in el:
            tag = self._local_tag(child)
            if tag == "annotation":
                elem.annotation = self._parse_annotation(child)
                break

        for child in el:
            tag = self._local_tag(child)
            if tag == "complexType":
                elem.inline_type = self._parse_complex_type(child, target_ns, ns_map)
                if elem.inline_type.content:
                    elem.children = [elem.inline_type.content]
                elem.attributes = list(elem.inline_type.attributes)
                break

        return elem

    # --- complexType parsing ---

    def _parse_complex_type(
        self,
        ct_el: etree._Element,
        target_ns: str,
        ns_map: dict[str, str],
    ) -> XsdComplexType:
        ct = XsdComplexType(
            name=ct_el.get("name", ""),
            namespace=target_ns,
            is_abstract=ct_el.get("abstract", "false").lower() == "true",
            is_mixed=ct_el.get("mixed", "false").lower() == "true",
        )

        for child in ct_el:
            tag = self._local_tag(child)
            if tag == "annotation":
                ct.annotation = self._parse_annotation(child)
            elif tag in ("sequence", "choice", "all"):
                ct.content = self._parse_compositor(child, target_ns, ns_map)
            elif tag == "complexContent":
                self._parse_complex_content(child, ct, target_ns, ns_map)
            elif tag == "simpleContent":
                self._parse_simple_content(child, ct, target_ns, ns_map)
            elif tag == "attribute":
                ct.attributes.append(self._parse_attribute(child, ns_map))

        return ct

    def _parse_complex_content(
        self,
        cc_el: etree._Element,
        ct: XsdComplexType,
        target_ns: str,
        ns_map: dict[str, str],
    ) -> None:
        for child in cc_el:
            tag = self._local_tag(child)
            if tag in ("extension", "restriction"):
                base = child.get("base", "")
                ct.base_type = base
                prefix, _ = self._split_qname(base)
                ct.base_namespace = ns_map.get(prefix, target_ns) if prefix else target_ns

                for sub in child:
                    stag = self._local_tag(sub)
                    if stag in ("sequence", "choice", "all"):
                        ct.content = self._parse_compositor(sub, target_ns, ns_map)
                    elif stag == "attribute":
                        ct.attributes.append(self._parse_attribute(sub, ns_map))
                    elif stag == "annotation":
                        if ct.annotation is None:
                            ct.annotation = self._parse_annotation(sub)

    def _parse_simple_content(
        self,
        sc_el: etree._Element,
        ct: XsdComplexType,
        target_ns: str,
        ns_map: dict[str, str],
    ) -> None:
        for child in sc_el:
            tag = self._local_tag(child)
            if tag in ("extension", "restriction"):
                base = child.get("base", "")
                ct.base_type = base
                prefix, _ = self._split_qname(base)
                ct.base_namespace = ns_map.get(prefix, target_ns) if prefix else target_ns
                for sub in child:
                    stag = self._local_tag(sub)
                    if stag == "attribute":
                        ct.attributes.append(self._parse_attribute(sub, ns_map))

    # --- Compositor parsing ---

    def _parse_compositor(
        self,
        comp_el: etree._Element,
        target_ns: str,
        ns_map: dict[str, str],
    ) -> XsdCompositor:
        tag = self._local_tag(comp_el)
        kind_map = {
            "sequence": CompositorKind.SEQUENCE,
            "choice": CompositorKind.CHOICE,
            "all": CompositorKind.ALL,
        }
        comp = XsdCompositor(kind=kind_map.get(tag, CompositorKind.SEQUENCE))
        comp.min_occurs = int(comp_el.get("minOccurs", "1"))
        max_str = comp_el.get("maxOccurs", "1")
        comp.max_occurs = -1 if max_str == "unbounded" else int(max_str)

        for child in comp_el:
            ctag = self._local_tag(child)
            if ctag == "element":
                comp.elements.append(self._parse_element(child, target_ns, ns_map))
            elif ctag in ("sequence", "choice", "all"):
                comp.compositors.append(self._parse_compositor(child, target_ns, ns_map))

        return comp

    # --- Attribute parsing ---

    def _parse_attribute(
        self,
        attr_el: etree._Element,
        ns_map: dict[str, str],
    ) -> XsdAttribute:
        use_str = attr_el.get("use", "optional")
        use_map = {
            "required": AttributeUse.REQUIRED,
            "optional": AttributeUse.OPTIONAL,
            "prohibited": AttributeUse.PROHIBITED,
        }
        # Support xs:attribute ref="..." — use ref local name as attribute name
        name = attr_el.get("name", "")
        if not name:
            ref = attr_el.get("ref", "")
            if ref:
                _, name = self._split_qname(ref)

        attr = XsdAttribute(
            name=name,
            type_ref=attr_el.get("type", ""),
            use=use_map.get(use_str, AttributeUse.OPTIONAL),
            default=attr_el.get("default"),
            fixed=attr_el.get("fixed"),
        )
        for child in attr_el:
            if self._local_tag(child) == "annotation":
                attr.annotation = self._parse_annotation(child)
                break
        return attr

    # --- simpleType parsing ---

    def _parse_simple_type(
        self,
        st_el: etree._Element,
        target_ns: str,
    ) -> XsdSimpleType:
        st = XsdSimpleType(
            name=st_el.get("name", ""),
            namespace=target_ns,
        )
        for child in st_el:
            tag = self._local_tag(child)
            if tag == "annotation":
                st.annotation = self._parse_annotation(child)
            elif tag == "restriction":
                st.restriction_base = child.get("base", "")
                for enum_el in child:
                    if self._local_tag(enum_el) == "enumeration":
                        val = enum_el.get("value", "")
                        if val:
                            st.enumerations.append(val)
        return st

    # --- Annotation parsing ---

    def _parse_annotation(self, ann_el: etree._Element) -> XsdAnnotation:
        ann = XsdAnnotation()
        for child in ann_el:
            if self._local_tag(child) == "documentation":
                text = (child.text or "").strip()
                lang = child.get("{http://www.w3.org/XML/1998/namespace}lang", "")
                ann.add_doc(text, lang)
        return ann

    # --- Utilities ---

    @staticmethod
    def _local_tag(el: etree._Element) -> str:
        tag = el.tag
        if isinstance(tag, str) and tag.startswith("{"):
            return tag.split("}", 1)[1]
        return str(tag)

    @staticmethod
    def _split_qname(qname: str) -> tuple[str, str]:
        if ":" in qname:
            parts = qname.split(":", 1)
            return parts[0], parts[1]
        return "", qname

    @staticmethod
    def _build_ns_map(root: etree._Element) -> dict[str, str]:
        ns_map: dict[str, str] = {}
        if root.nsmap:
            for prefix, uri in root.nsmap.items():
                if prefix is not None and uri is not None:
                    ns_map[prefix] = uri
        return ns_map


# --- Convenience functions ---

def parse_schema(
    schema_path: str,
    registry: Optional[SchemaRegistry] = None,
) -> XsdSchema:
    parser = XsdParser(registry)
    return parser.parse_file(schema_path)


def parse_schema_with_imports(
    schema_path: str,
) -> tuple[XsdSchema, SchemaRegistry]:
    registry = SchemaRegistry()
    parser = XsdParser(registry)
    schema = parser.parse_file(schema_path)
    return schema, registry
