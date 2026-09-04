from lorex.main import AppContainer
from lorex.postprocess import PostProcessor


def test_app_container_builds_physical_postprocessor_for_worker_pipeline(monkeypatch) -> None:
    monkeypatch.delenv("LOREX_ENABLE_MOCK_API", raising=False)
    container = AppContainer.build(None)
    try:
        assert isinstance(container.postprocessor, PostProcessor)
    finally:
        container.close()
