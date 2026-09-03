from __future__ import annotations

from lorex.library.media import MediaAction, MediaProbe, choose_media_action


def test_valid_m4b_is_preserved_without_reencoding() -> None:
    assert choose_media_action(MediaProbe(container="mov,mp4,m4a,3gp,3g2,mj2", audio_codec="aac", valid=True)) is MediaAction.PRESERVE


def test_compatible_audio_in_other_container_is_remuxed() -> None:
    assert choose_media_action(MediaProbe(container="matroska,webm", audio_codec="aac", valid=True)) is MediaAction.REMUX


def test_unsupported_audio_codec_requires_transcode() -> None:
    assert choose_media_action(MediaProbe(container="mp3", audio_codec="mp3", valid=True)) is MediaAction.TRANSCODE
