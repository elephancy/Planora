"""ElementTree-compatible construction with hardened document parsing."""
from xml.etree.ElementTree import Element, ElementTree, ParseError, SubElement, indent, tostring  # nosemgrep: python.lang.security.use-defused-xml
# The stdlib names above only construct/serialize trees; every input parser below
# uses defusedxml and rejects DTDs, entities and external references.
from defusedxml import ElementTree as _safe
from defusedxml.common import DefusedXmlException


def parse(source):
    try:
        return _safe.parse(source, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except DefusedXmlException as exc:
        raise ParseError("XML declarations/entities are forbidden") from exc


def fromstring(text):
    try:
        return _safe.fromstring(text, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except DefusedXmlException as exc:
        raise ParseError("XML declarations/entities are forbidden") from exc


def iterparse(source, events=None):
    try:
        yield from _safe.iterparse(source, events=events, forbid_dtd=True,
                                   forbid_entities=True, forbid_external=True)
    except DefusedXmlException as exc:
        raise ParseError("XML declarations/entities are forbidden") from exc
