"""Internal XSD schema model — dataclasses for all constructs.

JSON-serializable model used by MCP server (parse_xsd -> JSON)
and Streamlit web app.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CompositorKind(str, Enum):
    SEQUENCE = "sequence"
    CHOICE = "choice"
    ALL = "all"


class AttributeUse(str, Enum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    PROHIBITED = "prohibited"


class XsdAnnotation:
    """xs:annotation/xs:documentation with multilingual support.

    Stores documentation strings keyed by xml:lang.
    Backward-compatible: ``annotation.documentation`` still returns a str.
    """

    __slots__ = ("_docs",)

    def __init__(self) -> None:
        self._docs: dict[str, str] = {}

    # --- public API ---

    def add_doc(self, text: str, lang: str = "") -> None:
        """Add documentation for a specific language."""
        if text:
            self._docs[lang] = text

    def get_doc(self, preferred_lang: str = "") -> str:
        """Get documentation with fallback: preferred → 'en' → '' → first."""
        if not self._docs:
            return ""
        if preferred_lang and preferred_lang in self._docs:
            return self._docs[preferred_lang]
        if "en" in self._docs:
            return self._docs["en"]
        if "" in self._docs:
            return self._docs[""]
        return next(iter(self._docs.values()))

    def has_content(self) -> bool:
        return bool(self._docs)

    @property
    def available_langs(self) -> list[str]:
        return list(self._docs.keys())

    # --- backward-compatible properties ---

    @property
    def documentation(self) -> str:
        return self.get_doc()

    @documentation.setter
    def documentation(self, value: str) -> None:
        if value:
            self._docs[""] = value
        elif "" in self._docs:
            del self._docs[""]

    @property
    def lang(self) -> str:
        if self._docs:
            return next(iter(self._docs))
        return ""

    @lang.setter
    def lang(self, value: str) -> None:
        if "" in self._docs and value:
            self._docs[value] = self._docs.pop("")

    def __bool__(self) -> bool:
        return self.has_content()

    def __repr__(self) -> str:
        return f"XsdAnnotation({self._docs!r})"


@dataclass
class XsdAttribute:
    name: str = ""
    type_ref: str = ""
    use: AttributeUse = AttributeUse.OPTIONAL
    default: Optional[str] = None
    fixed: Optional[str] = None
    annotation: Optional[XsdAnnotation] = None

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "type_ref": self.type_ref,
            "use": self.use.value,
        }
        if self.default is not None:
            d["default"] = self.default
        if self.fixed is not None:
            d["fixed"] = self.fixed
        if self.annotation:
            d["annotation"] = self.annotation.documentation
        return d


@dataclass
class XsdElement:
    name: str = ""
    namespace: str = ""
    type_ref: str = ""
    type_namespace: str = ""
    min_occurs: int = 1
    max_occurs: int = 1         # -1 = unbounded
    is_ref: bool = False
    ref_namespace: str = ""
    is_abstract: bool = False
    has_text_content: bool = False
    substitution_group: str = ""
    substitution_group_namespace: str = ""
    annotation: Optional[XsdAnnotation] = None
    inline_type: Optional[XsdComplexType] = None
    children: list[XsdCompositor] = field(default_factory=list)
    attributes: list[XsdAttribute] = field(default_factory=list)

    @property
    def is_required(self) -> bool:
        return self.min_occurs >= 1

    @property
    def is_repeating(self) -> bool:
        return self.max_occurs == -1 or self.max_occurs > 1

    @property
    def multiplicity_label(self) -> str:
        if self.min_occurs == 0 and self.max_occurs == -1:
            return "0..\u221e"
        if self.min_occurs == 1 and self.max_occurs == -1:
            return "1..\u221e"
        if self.min_occurs == 0 and self.max_occurs == 1:
            return "0..1"
        if self.min_occurs == 1 and self.max_occurs == 1:
            return ""
        if self.max_occurs == -1:
            return f"{self.min_occurs}..\u221e"
        return f"{self.min_occurs}..{self.max_occurs}"

    @property
    def has_children(self) -> bool:
        return bool(self.children) or self.inline_type is not None

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "namespace": self.namespace,
            "type_ref": self.type_ref,
            "min_occurs": self.min_occurs,
            "max_occurs": self.max_occurs,
            "is_ref": self.is_ref,
            "is_required": self.is_required,
            "is_repeating": self.is_repeating,
            "has_text_content": self.has_text_content,
            "has_children": self.has_children,
            "multiplicity": self.multiplicity_label,
        }
        if self.annotation:
            d["annotation"] = self.annotation.documentation
        if self.attributes:
            d["attributes"] = [a.to_dict() for a in self.attributes]
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        if self.inline_type:
            d["inline_type"] = self.inline_type.to_dict()
        return d


@dataclass
class XsdCompositor:
    kind: CompositorKind = CompositorKind.SEQUENCE
    min_occurs: int = 1
    max_occurs: int = 1
    elements: list[XsdElement] = field(default_factory=list)
    compositors: list[XsdCompositor] = field(default_factory=list)

    @property
    def is_required(self) -> bool:
        return self.min_occurs >= 1

    @property
    def multiplicity_label(self) -> str:
        if self.min_occurs == 0 and self.max_occurs == -1:
            return "0..\u221e"
        if self.min_occurs == 1 and self.max_occurs == -1:
            return "1..\u221e"
        if self.min_occurs == 0 and self.max_occurs == 1:
            return "0..1"
        return ""

    @property
    def all_children(self) -> list:
        result: list = []
        result.extend(self.elements)
        result.extend(self.compositors)
        return result

    def to_dict(self) -> dict:
        d = {
            "kind": self.kind.value,
            "min_occurs": self.min_occurs,
            "max_occurs": self.max_occurs,
            "multiplicity": self.multiplicity_label,
        }
        if self.elements:
            d["elements"] = [e.to_dict() for e in self.elements]
        if self.compositors:
            d["compositors"] = [c.to_dict() for c in self.compositors]
        return d


@dataclass
class XsdComplexType:
    name: str = ""
    namespace: str = ""
    base_type: str = ""
    base_namespace: str = ""
    is_abstract: bool = False
    is_mixed: bool = False
    annotation: Optional[XsdAnnotation] = None
    content: Optional[XsdCompositor] = None
    attributes: list[XsdAttribute] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "namespace": self.namespace,
            "is_abstract": self.is_abstract,
        }
        if self.base_type:
            d["base_type"] = self.base_type
            d["base_namespace"] = self.base_namespace
        if self.annotation:
            d["annotation"] = self.annotation.documentation
        if self.content:
            d["content"] = self.content.to_dict()
        if self.attributes:
            d["attributes"] = [a.to_dict() for a in self.attributes]
        return d


@dataclass
class XsdSimpleType:
    name: str = ""
    namespace: str = ""
    restriction_base: str = ""
    enumerations: list[str] = field(default_factory=list)
    annotation: Optional[XsdAnnotation] = None

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "namespace": self.namespace,
            "restriction_base": self.restriction_base,
        }
        if self.enumerations:
            d["enumerations"] = self.enumerations
        if self.annotation:
            d["annotation"] = self.annotation.documentation
        return d


@dataclass
class XsdImport:
    namespace: str = ""
    schema_location: str = ""


@dataclass
class XsdSchema:
    target_namespace: str = ""
    schema_location: str = ""
    version: str = ""
    annotation: Optional[XsdAnnotation] = None
    imports: list[XsdImport] = field(default_factory=list)
    elements: list[XsdElement] = field(default_factory=list)
    complex_types: list[XsdComplexType] = field(default_factory=list)
    simple_types: list[XsdSimpleType] = field(default_factory=list)
    ns_prefix_map: dict[str, str] = field(default_factory=dict)  # URI -> prefix

    def find_complex_type(self, name: str) -> Optional[XsdComplexType]:
        for ct in self.complex_types:
            if ct.name == name:
                return ct
        return None

    def find_element(self, name: str) -> Optional[XsdElement]:
        for el in self.elements:
            if el.name == name:
                return el
        return None

    def to_dict(self) -> dict:
        d = {
            "target_namespace": self.target_namespace,
            "schema_location": self.schema_location,
        }
        if self.annotation:
            d["annotation"] = self.annotation.documentation
        if self.imports:
            d["imports"] = [{"namespace": i.namespace, "schema_location": i.schema_location}
                           for i in self.imports]
        if self.elements:
            d["elements"] = [e.to_dict() for e in self.elements]
        if self.complex_types:
            d["complex_types"] = [ct.to_dict() for ct in self.complex_types]
        if self.simple_types:
            d["simple_types"] = [st.to_dict() for st in self.simple_types]
        return d
