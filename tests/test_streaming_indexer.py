import lorex.indexer.grouping as grouping


def test_streaming_header_grouper_api_exists():
    assert hasattr(grouping, "StreamingHeaderGrouper")
    assert hasattr(grouping, "normalize_header")
