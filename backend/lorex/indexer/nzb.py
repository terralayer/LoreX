from __future__ import annotations

from xml.etree.ElementTree import Element, SubElement, tostring

from lorex.domain import ReleaseCandidate

_NZB_NS = "http://www.newzbin.com/DTD/2003/nzb"


def build_nzb(candidate: ReleaseCandidate) -> str:
    root = Element("nzb", {"xmlns": _NZB_NS})
    file_el = SubElement(root, "file", {"poster": "LoreX", "subject": candidate.subject_stem})
    groups_el = SubElement(file_el, "groups")
    groups = sorted({header.group for header in candidate.headers})
    for group in groups:
        SubElement(groups_el, "group").text = group

    segments_el = SubElement(file_el, "segments")
    for number, header in enumerate(candidate.headers, start=1):
        segment = SubElement(segments_el, "segment", {"bytes": str(header.bytes), "number": str(number)})
        segment.text = header.message_id.strip("<>")

    return tostring(root, encoding="unicode", xml_declaration=True)
