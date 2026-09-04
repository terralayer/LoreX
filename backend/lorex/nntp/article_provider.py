from __future__ import annotations

from collections.abc import Callable, Iterator

from lorex.downloader.provider import ArticleUnavailable, ProviderTemporaryError
from lorex.nntp.client import NntpClient
from lorex.nntp.errors import NntpArticleMissing, NntpTemporaryError
from lorex.nntp.models import NntpProvider
from lorex.nntp.yenc import decode_yenc_stream


class NntpArticleProvider:
    def __init__(
        self,
        provider: NntpProvider,
        *,
        client_factory: Callable[[NntpProvider], object] | None = None,
        output_chunk_size: int = 65_536,
        max_line_length: int = 65_536,
    ) -> None:
        if output_chunk_size <= 0:
            raise ValueError("output_chunk_size must be positive")
        self.provider = provider
        self.client_factory = client_factory or self._default_client_factory
        self.output_chunk_size = output_chunk_size
        self.max_line_length = max_line_length

    @staticmethod
    def _default_client_factory(provider: NntpProvider) -> NntpClient:
        return NntpClient(provider.host, provider.port)

    def stream_article(self, message_id: str) -> Iterator[bytes]:
        try:
            with self.client_factory(self.provider) as client:
                if self.provider.username is not None or self.provider.password is not None:
                    if self.provider.username is None or self.provider.password is None:
                        raise ValueError("NNTP username and password must be configured together")
                    client.authenticate(self.provider.username, self.provider.password)
                yield from decode_yenc_stream(
                    client.body(message_id),
                    output_chunk_size=self.output_chunk_size,
                    max_line_length=self.max_line_length,
                )
        except NntpArticleMissing as exc:
            raise ArticleUnavailable(message_id) from exc
        except NntpTemporaryError as exc:
            raise ProviderTemporaryError("NNTP provider is temporarily unavailable") from exc
