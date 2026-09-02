from xml.etree import ElementTree

from lorex.domain import ArticleHeader
from lorex.indexer.classifier import classify_audiobook
from lorex.indexer.grouping import group_headers
from lorex.indexer.nzb import build_nzb


def test_groups_and_classifies_audiobook_release(mock_headers):
    headers = [ArticleHeader(**item) for item in mock_headers]
    candidates = group_headers(headers)
    audiobook = next(item for item in candidates if "Project Hail Mary" in item.subject_stem)

    assert len(audiobook.headers) == 3
    assert classify_audiobook(audiobook) >= 0.8

    nzb = build_nzb(audiobook)
    root = ElementTree.fromstring(nzb)
    assert root.tag.endswith("nzb")
    for header in audiobook.headers:
        assert header.message_id.strip("<>") in nzb


def test_rejects_obvious_video_release(mock_headers):
    headers = [ArticleHeader(**item) for item in mock_headers]
    video = next(item for item in group_headers(headers) if "Example.Movie" in item.subject_stem)
    assert classify_audiobook(video) < 0.8
