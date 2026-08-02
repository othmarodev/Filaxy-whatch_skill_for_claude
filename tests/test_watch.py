"""End-to-end routing of --detail through watch.py on a local clip."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

WATCH = Path(__file__).resolve().parent.parent / "skills" / "filaxy-watch" / "scripts" / "watch.py"


def _run(clip: Path, *args: str, env_extra: dict | None = None) -> str:
    env = dict(os.environ)
    env.pop("FILAXY_WATCH_DETAIL", None)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, str(WATCH), str(clip), "--no-whisper", *args],
        capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_efficient_uses_keyframe_engine(cut_clip: Path):
    out = _run(cut_clip, "--detail", "efficient")
    assert "(keyframe" in out
    assert "**Detail:** efficient" in out


def test_balanced_uses_scene_engine(cut_clip: Path):
    out = _run(cut_clip, "--detail", "balanced")
    assert "(scene" in out
    assert "**Detail:** balanced" in out


def test_token_burner_uses_scene_engine(cut_clip: Path):
    out = _run(cut_clip, "--detail", "token-burner")
    assert "(scene" in out


def test_transcript_skips_frames(cut_clip: Path):
    out = _run(cut_clip, "--detail", "transcript")
    assert "skipped" in out
    assert "frame_0000.jpg" not in out


def test_flag_overrides_env(cut_clip: Path):
    out = _run(cut_clip, "--detail", "efficient", env_extra={"FILAXY_WATCH_DETAIL": "balanced"})
    assert "(keyframe" in out


def test_default_is_balanced(cut_clip: Path):
    out = _run(cut_clip)  # no flag, FILAXY_WATCH_DETAIL cleared
    assert "**Detail:** balanced" in out
    assert "(scene" in out


def test_timestamps_add_cue_frames_to_detail(cut_clip: Path):
    out = _run(cut_clip, "--detail", "balanced", "--timestamps", "1,3")
    assert "reason=transcript-cue" in out
    assert "reason=scene-change" in out  # detail frames still present (additive)


def test_timestamps_with_transcript_detail_is_cue_only(cut_clip: Path):
    out = _run(cut_clip, "--detail", "transcript", "--timestamps", "1,3")
    assert "reason=transcript-cue" in out
    assert "reason=scene-change" not in out
    assert "reason=keyframe" not in out


def _frame_lines(out: str) -> int:
    return sum(1 for line in out.splitlines() if "/frames/frame_" in line and "(t=" in line)


def test_dedup_collapses_static_by_default(static_clip: Path):
    out = _run(static_clip)  # solid blue → identical frames collapse to one
    assert "near-duplicate" in out
    assert _frame_lines(out) == 1


def test_no_dedup_preserves_static_frames(static_clip: Path):
    out = _run(static_clip, "--no-dedup")
    assert "near-duplicate" not in out
    assert _frame_lines(out) > 1


def test_multi_source_produces_one_section_per_video(cut_clip: Path, static_clip: Path, tmp_path: Path):
    # _run only accepts one clip positionally; invoke the CLI directly for two.
    proc_out = _run2(cut_clip, static_clip, "--detail", "efficient", out_dir=tmp_path / "multi")
    assert "## Video 1/2:" in proc_out
    assert "## Video 2/2:" in proc_out
    assert proc_out.count("### Report") == 2
    # Each video's frames land in its own numbered sub-directory, never colliding.
    assert (tmp_path / "multi" / "video_1" / "frames").is_dir()
    assert (tmp_path / "multi" / "video_2" / "frames").is_dir()


def _run2(clip_a: Path, clip_b: Path, *args: str, out_dir: Path) -> str:
    env = dict(os.environ)
    env.pop("FILAXY_WATCH_DETAIL", None)
    proc = subprocess.run(
        [sys.executable, str(WATCH), str(clip_a), str(clip_b), "--no-whisper", "--out-dir", str(out_dir), *args],
        capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_single_source_keeps_flat_layout(cut_clip: Path, tmp_path: Path):
    out_dir = tmp_path / "single"
    out = _run(cut_clip, "--detail", "efficient", "--out-dir", str(out_dir))
    assert "## Video 1/1" not in out  # single source: no multi-video wrapper
    assert "# watch: video report" in out
    assert (out_dir / "frames").is_dir()  # flat layout, not out_dir/video_1/frames
