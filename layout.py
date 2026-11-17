"""Render klip vertikal 9:16 (1080x1920): footage utama di atas, facecam di bawah.

Sumber adalah satu video stream (16:9) yang di pojoknya ada facecam.
Kedua panel memenuhi kanvas tanpa celah, seperti format klip streamer:
  - footage utama: selebar 1080, tinggi proporsional, di bagian atas,
  - facecam: dipotong dari kotaknya lalu diskalakan + crop tengah agar
    mengisi sisa kanvas di bawahnya persis sampai 1920.
Subtitle .ass dibakar (burn-in) di akhir rantai filter.
"""

from __future__ import annotations

import json
import subprocess

CANVAS_W, CANVAS_H = 1080, 1920


def probe_size(video_path: str) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", video_path],
        capture_output=True, text=True, check=True,
    ).stdout
    s = json.loads(out)["streams"][0]
    return int(s["width"]), int(s["height"])


def main_panel_height(src_w: int, src_h: int) -> int:
    """Tinggi panel footage setelah diskalakan selebar 1080 (dibulatkan genap)."""
    h = round(CANVAS_W * src_h / src_w)
    return h - (h % 2)


def panel_height(src_w: int, src_h: int, top_ratio: float | None = None) -> int:
    """Tinggi panel footage: proporsional, atau rasio kanvas bila diminta."""
    if top_ratio and top_ratio > 0:
        h = round(CANVAS_H * top_ratio)
    else:
        h = main_panel_height(src_w, src_h)
    h = max(200, min(CANVAS_H - 200, h))
    return h - (h % 2)


def _main_filter(top_h: int, fit_mode: str) -> str:
    """Filter panel footage sesuai mode isi: crop / fit-blur / fit-hitam."""
    if fit_mode == "fit-blur":
        return (
            f"[0:v]split=2[msrc][mfg];"
            f"[msrc]scale={CANVAS_W}:{top_h}:force_original_aspect_ratio=increase,"
            f"crop={CANVAS_W}:{top_h},gblur=sigma=40,eq=brightness=-0.08[mbg];"
            f"[mfg]scale={CANVAS_W}:{top_h}:force_original_aspect_ratio=decrease[mf];"
            f"[mbg][mf]overlay=(W-w)/2:(H-h)/2[main];"
        )
    if fit_mode == "fit-hitam":
        return (
            f"[0:v]scale={CANVAS_W}:{top_h}:force_original_aspect_ratio=decrease,"
            f"pad={CANVAS_W}:{top_h}:(ow-iw)/2:(oh-ih)/2:black[main];"
        )
    # crop: isi penuh panel, potong sisi yang berlebih (default)
    return (
        f"[0:v]scale={CANVAS_W}:{top_h}:force_original_aspect_ratio=increase,"
        f"crop={CANVAS_W}:{top_h}[main];"
    )


def render_clip(
    video_path: str,
    start: float,
    end: float,
    facecam_box: tuple[int, int, int, int],
    ass_path: str | None,
    out_path: str,
    crf: int = 20,
    fit_mode: str = "crop",
    top_ratio: float | None = None,
) -> str:
    """Potong segmen [start, end] dan render ke layout vertikal. facecam_box = (x, y, w, h) piksel."""
    fx, fy, fw, fh = facecam_box
    dur = end - start
    src_w, src_h = probe_size(video_path)
    top_h = panel_height(src_w, src_h, top_ratio)
    cam_h = CANVAS_H - top_h
    fc = (
        _main_filter(top_h, fit_mode) +
        f"[0:v]crop={fw}:{fh}:{fx}:{fy},"
        f"scale={CANVAS_W}:{cam_h}:force_original_aspect_ratio=increase,"
        f"crop={CANVAS_W}:{cam_h}[cam];"
        f"[main][cam]vstack=inputs=2[stack]"
    )
    if ass_path:
        ass_escaped = ass_path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        fc += f";[stack]subtitles='{ass_escaped}'[vout]"
    else:
        fc += ";[stack]null[vout]"

    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-ss", f"{start:.2f}", "-i", video_path,
        "-filter_complex", fc,
        "-map", "[vout]", "-map", "0:a?",
        "-t", f"{dur:.2f}",
        "-c:v", "libx264", "-crf", str(crf), "-preset", "medium",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        out_path,
    ]
    subprocess.run(cmd, check=True)
    return out_path
