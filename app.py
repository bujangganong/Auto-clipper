#!/usr/bin/env python3
"""Auto Clipper — tampilan web lokal (Gradio), mesin yang sama dengan clipper.py.

Jalankan:  python app.py            -> buka http://127.0.0.1:7860
           python app.py --lan      -> bisa dibuka dari HP di Wi-Fi yang sama

Seret file video, atur opsi, klik Proses. Klip hasil muncul sebagai file
yang bisa diunduh, lengkap dengan galeri thumbnail untuk mengintip isinya.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import gradio as gr

from clipper import detect_facecam, parse_facecam, probe_size
from highlights import extract_audio_samples, find_highlights
from layout import main_panel_height, render_clip
from subtitles import transcribe_words, words_to_ass


def _thumbnail(video_path: str, at_sec: float, out_path: str) -> str | None:
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", f"{at_sec:.1f}", "-i", video_path,
             "-frames:v", "1", "-vf", "scale=270:-2", out_path],
            check=True,
        )
        return out_path
    except Exception:
        return None


def proses(video_path, num, facecam_mode, fx, fy, fw, fh, model, lang, pakai_subs, progress=gr.Progress()):
    if not video_path:
        raise gr.Error("Pilih dulu file videonya.")
    src = Path(video_path)
    out_dir = Path("clips") / src.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    width, height = probe_size(str(src))
    progress(0.05, desc="Menentukan posisi facecam...")
    if facecam_mode == "auto":
        box = detect_facecam(str(src), width, height)
    else:
        box = parse_facecam(f"{fx},{fy},{fw},{fh}", width, height)

    progress(0.15, desc="Menganalisis suara untuk momen seru...")
    samples = extract_audio_samples(str(src))
    moments = find_highlights(samples, num_clips=int(num))
    if not moments:
        raise gr.Error("Tidak ada momen seru yang ditemukan di video ini.")

    words = []
    if pakai_subs:
        progress(0.35, desc="Mentranskrip omongan (Whisper)...")
        words = transcribe_words(str(src), model_size=model, language=lang or None)

    sub_y = main_panel_height(width, height) + 60
    hasil, thumbs = [], []
    for i, m in enumerate(moments, 1):
        progress(0.4 + 0.55 * i / len(moments), desc=f"Merender klip {i} dari {len(moments)}...")
        ass_path = None
        if words:
            ass_path = str(out_dir / f"klip-{i:02d}.ass")
            words_to_ass(words, m["start"], m["end"], ass_path, pos_y=sub_y)
        out_path = str(out_dir / f"klip-{i:02d}.mp4")
        render_clip(str(src), m["start"], m["end"], box, ass_path, out_path)
        hasil.append(out_path)
        thumb = _thumbnail(out_path, min(3.0, (m["end"] - m["start"]) / 2), str(out_dir / f"klip-{i:02d}.jpg"))
        if thumb:
            thumbs.append((thumb, f"Klip {i}: {m['start']:.0f}s - {m['end']:.0f}s"))
    ringkasan = f"Selesai: {len(hasil)} klip dari {src.name} (facecam di {box}). Tersimpan juga di folder {out_dir}/"
    return hasil, thumbs, ringkasan


with gr.Blocks(title="Auto Clipper") as demo:
    gr.Markdown("# ✂️ Auto Clipper\nPotong momen seru dari video stream jadi klip vertikal 9:16 — footage di atas, facecam di bawah, subtitle kata per kata.")
    with gr.Row():
        with gr.Column():
            video_in = gr.Video(label="Video stream sumber", sources=["upload"])
            num = gr.Slider(1, 10, value=5, step=1, label="Jumlah klip")
            facecam_mode = gr.Radio(["auto", "manual"], value="auto", label="Posisi facecam")
            with gr.Row():
                fx = gr.Number(value=0.78, label="x (manual)")
                fy = gr.Number(value=0.72, label="y (manual)")
                fw = gr.Number(value=0.20, label="w (manual)")
                fh = gr.Number(value=0.26, label="h (manual)")
            model = gr.Dropdown(["tiny", "base", "small", "medium", "large-v3"], value="small", label="Model Whisper")
            lang = gr.Textbox(value="id", label="Bahasa transkrip (id/en/...)")
            pakai_subs = gr.Checkbox(value=True, label="Pakai subtitle")
            tombol = gr.Button("✂️ Proses", variant="primary")
        with gr.Column():
            files_out = gr.File(label="Klip hasil (klik untuk unduh)", file_count="multiple")
            gallery_out = gr.Gallery(label="Intip thumbnail klip", columns=3)
            status = gr.Textbox(label="Status", interactive=False)
    tombol.click(
        proses,
        inputs=[video_in, num, facecam_mode, fx, fy, fw, fh, model, lang, pakai_subs],
        outputs=[files_out, gallery_out, status],
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lan", action="store_true", help="Izinkan akses dari perangkat lain di Wi-Fi yang sama")
    args = ap.parse_args()
    demo.launch(server_name="0.0.0.0" if args.lan else "127.0.0.1", server_port=7860)
