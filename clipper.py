#!/usr/bin/env python3
"""Auto Clipper — potong otomatis momen seru dari video stream.

Alur:
  1. Deteksi momen seru dari lonjakan suara (highlights.py)
  2. Transkrip omongan per kata dengan Whisper (subtitles.py)
  3. Render tiap momen jadi klip vertikal 9:16: footage di atas,
     facecam di bawah, subtitle kata-per-kata besar di tengah (layout.py)

Contoh:
  python clipper.py stream.mp4 --facecam 0.78,0.72,0.20,0.26 --num 5
  python clipper.py stream.mp4 --facecam auto --num 3 --model small --lang id
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from highlights import extract_audio_samples, find_highlights
from layout import main_panel_height, render_clip
from subtitles import transcribe_words, words_to_ass


def probe_size(video_path: str) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", video_path],
        capture_output=True, text=True, check=True,
    ).stdout
    s = json.loads(out)["streams"][0]
    return int(s["width"]), int(s["height"])


def detect_facecam(video_path: str, width: int, height: int) -> tuple[int, int, int, int]:
    """Tebak kotak facecam: sampel beberapa frame, cari wajah yang posisinya konsisten.

    Kotak diperbesar ~1.8x dari wajah agar dapat area kamera + bahu.
    """
    import cv2
    import numpy as np

    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    boxes = []
    for frac in (0.1, 0.25, 0.4, 0.55, 0.7, 0.85):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * frac))
        ok, frame = cap.read()
        if not ok:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        for (x, y, w, h) in cascade.detectMultiScale(gray, 1.1, 5, minSize=(60, 60)):
            boxes.append((x, y, w, h))
    cap.release()
    if not boxes:
        raise RuntimeError(
            "Facecam tidak terdeteksi otomatis. Beri manual: --facecam x,y,w,h "
            "(relatif 0-1, mis. 0.78,0.72,0.20,0.26 untuk pojok kanan bawah)."
        )
    x, y, w, h = np.median(np.array(boxes), axis=0)
    cx, cy = x + w / 2, y + h / 2
    nw, nh = w * 1.8, h * 1.8
    nx = int(max(0, min(cx - nw / 2, width - nw)))
    ny = int(max(0, min(cy - nh / 2, height - nh)))
    return nx, ny, int(nw), int(nh)


def parse_facecam(spec: str, width: int, height: int) -> tuple[int, int, int, int]:
    parts = [float(p) for p in spec.split(",")]
    if len(parts) != 4:
        raise ValueError("--facecam harus berisi 4 angka: x,y,w,h")
    x, y, w, h = parts
    if max(parts) <= 1.0:  # relatif 0-1
        return int(x * width), int(y * height), int(w * width), int(h * height)
    return int(x), int(y), int(w), int(h)  # piksel


def main() -> int:
    ap = argparse.ArgumentParser(description="Auto clipper momen seru untuk Shorts/TikTok")
    ap.add_argument("video", help="File video stream sumber (mp4, mkv, ...)")
    ap.add_argument("--out", default="clips", help="Folder hasil (default: clips)")
    ap.add_argument("--num", type=int, default=5, help="Jumlah klip (default: 5)")
    ap.add_argument("--facecam", default="auto",
                    help="'auto' atau x,y,w,h relatif 0-1 / piksel (default: auto)")
    ap.add_argument("--model", default="small", help="Model Whisper (default: small)")
    ap.add_argument("--lang", default="id", help="Bahasa transkrip, mis. id/en (default: id)")
    ap.add_argument("--no-subs", action="store_true", help="Lewati pembuatan subtitle")
    ap.add_argument("--fit", default="crop", choices=["crop", "fit-blur", "fit-hitam"],
                    help="Mode tampilan footage: crop = isi penuh potong sisi, fit-blur/fit-hitam = footage utuh berlatar (default: crop)")
    ap.add_argument("--top-ratio", type=float, default=None,
                    help="Tinggi panel footage sebagai rasio kanvas, mis. 0.5 (default: proporsional)")
    args = ap.parse_args()

    video = Path(args.video)
    if not video.exists():
        print(f"File tidak ditemukan: {video}", file=sys.stderr)
        return 1
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    width, height = probe_size(str(video))
    print(f"Video: {width}x{height}")

    if args.facecam == "auto":
        box = detect_facecam(str(video), width, height)
    else:
        box = parse_facecam(args.facecam, width, height)
    print(f"Kotak facecam (x,y,w,h piksel): {box}")

    print("Menganalisis suara untuk momen seru...")
    samples = extract_audio_samples(str(video))
    moments = find_highlights(samples, num_clips=args.num)
    if not moments:
        print("Tidak ada momen yang ditemukan.", file=sys.stderr)
        return 1
    for i, m in enumerate(moments, 1):
        print(f"  Momen {i}: {m['start']:.0f}s - {m['end']:.0f}s (skor {m['score']:.2f})")

    words = []
    if not args.no_subs:
        print("Mentranskrip omongan (Whisper)...")
        words = transcribe_words(str(video), model_size=args.model, language=args.lang)

    from layout import panel_height
    sub_y = panel_height(width, height, args.top_ratio) + 60  # subtitle tepat di bawah sambungan dua panel
    for i, m in enumerate(moments, 1):
        ass_path = None
        if words:
            ass_path = str(out_dir / f"klip-{i:02d}.ass")
            words_to_ass(words, m["start"], m["end"], ass_path, pos_y=sub_y)
        out_path = str(out_dir / f"klip-{i:02d}.mp4")
        print(f"Merender {out_path} ...")
        render_clip(str(video), m["start"], m["end"], box, ass_path, out_path,
                    fit_mode=args.fit, top_ratio=args.top_ratio)
    print(f"Selesai. {len(moments)} klip tersimpan di {out_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
