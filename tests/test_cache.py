"""Download cache: re-asking about the same URL should skip yt-dlp entirely."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "skills" / "filaxy-watch" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import download  # noqa: E402

URL = "https://www.youtube.com/watch?v=rlOpbu3Enkw"


def _capture_argv(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, *args, **kwargs):
        calls.append(list(cmd))
        return _Result()

    monkeypatch.setattr(download.subprocess, "run", fake_run)
    return calls


def test_cache_key_is_stable_and_kind_specific():
    a = download.cache_key(URL, audio_only=False)
    b = download.cache_key(URL, audio_only=False)
    c = download.cache_key(URL, audio_only=True)
    assert a == b
    assert a != c


def test_cache_miss_calls_yt_dlp_and_populates_cache(monkeypatch, tmp_path):
    calls = _capture_argv(monkeypatch)
    cache_dir = tmp_path / "cache"

    def fake_run(cmd, *args, **kwargs):
        calls.append(list(cmd))
        # Simulate yt-dlp writing the video file it was asked to produce.
        out_flag = cmd.index("-o")
        template = cmd[out_flag + 1]
        video_path = Path(template.replace("%(ext)s", "mp4"))
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.write_bytes(b"fake")

        class _Result:
            returncode = 0

        return _Result()

    monkeypatch.setattr(download.subprocess, "run", fake_run)

    result = download.download_url(URL, tmp_path / "download", cache_dir=cache_dir)
    assert len(calls) == 1, "cache miss must call yt-dlp exactly once"
    assert result["downloaded"] is True
    assert result["cached"] is False
    key = download.cache_key(URL, audio_only=False)
    assert (cache_dir / key / "video.mp4").exists()


def test_cache_hit_skips_yt_dlp_entirely(monkeypatch, tmp_path):
    calls = _capture_argv(monkeypatch)
    cache_dir = tmp_path / "cache"
    key = download.cache_key(URL, audio_only=False)
    cached_video = cache_dir / key / "video.mp4"
    cached_video.parent.mkdir(parents=True, exist_ok=True)
    cached_video.write_bytes(b"already here")

    result = download.download_url(URL, tmp_path / "download", cache_dir=cache_dir)

    assert calls == [], "cache hit must not shell out to yt-dlp at all"
    assert result["cached"] is True
    assert result["downloaded"] is False
    assert result["video_path"] == str(cached_video)


def test_no_cache_forces_fresh_download_even_with_a_hit(monkeypatch, tmp_path):
    calls = _capture_argv(monkeypatch)
    cache_dir = tmp_path / "cache"
    key = download.cache_key(URL, audio_only=False)
    (cache_dir / key).mkdir(parents=True, exist_ok=True)
    (cache_dir / key / "video.mp4").write_bytes(b"stale")

    # use_cache=False bypasses the cache lookup; _pick_video on the empty
    # out_dir returns None (no real yt-dlp ran), which raises — that's enough
    # to prove the cache hit above was never consulted.
    with pytest.raises(SystemExit):
        download.download_url(
            URL, tmp_path / "download", cache_dir=cache_dir, use_cache=False,
        )
    assert len(calls) == 1, "must have attempted a real yt-dlp call, not the cache"
