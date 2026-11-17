#!/usr/bin/env python3
"""Auto Clipper — tampilan web lokal (Gradio), mesin yang sama dengan clipper.py.

Jalankan:  python app.py            -> buka http://127.0.0.1:7860
           python app.py --lan      -> bisa dibuka dari HP di Wi-Fi yang sama

Seret file video, atur opsi, klik "1. Analisis + transkrip". Transkrip
tiap klip muncul sebagai teks yang bisa diedit (betulkan kata yang salah
dengar Whisper); klik "2. Render klip" untuk membuat videonya — timing
subtitle kata-per-kata menyesuaikan hasil editan secara otomatis.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import gradio as gr
from PIL import Image, ImageDraw

from clipper import detect_facecam, parse_facecam, probe_size
from highlights import extract_audio_samples, find_highlights, parse_ranges
from layout import main_panel_height, panel_height, render_clip
from subtitles import clip_words, retime_edited_words, transcribe_words, words_to_ass

MAX_CLIPS = 10


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


def _probe_duration(video_path: str) -> float:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True, check=True,
        )
        return float(out.stdout.strip())
    except Exception:
        return 0.0


def ambil_frame(video_path):
    """Ambil satu frame contoh dari video untuk memilih kotak facecam visual."""
    if not video_path:
        raise gr.Error("Upload dulu videonya, baru ambil frame contoh.")
    src = Path(video_path)
    prev_dir = Path("clips") / "_preview"
    prev_dir.mkdir(parents=True, exist_ok=True)
    frame_path = str(prev_dir / f"{src.stem}-frame.png")
    dur = _probe_duration(str(src))
    at = min(10.0, dur * 0.25) if dur > 0 else 5.0
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", f"{at:.1f}", "-i", str(src),
         "-frames:v", "1", frame_path],
        check=True,
    )
    width, height = probe_size(str(src))
    state = {"p1": None, "box_px": None, "frame": frame_path, "size": (width, height)}
    return frame_path, state, "Klik sudut kiri-atas kotak facecam di gambar, lalu klik sudut kanan-bawahnya."


def _gambar_kotak(state):
    img = Image.open(state["frame"]).convert("RGB")
    d = ImageDraw.Draw(img)
    w, h = img.size
    r = max(6, w // 160)
    if state.get("p1"):
        x, y = state["p1"]
        d.ellipse([x - r, y - r, x + r, y + r], outline=(255, 80, 80), width=4)
        d.line([x - r * 2, y, x + r * 2, y], fill=(255, 80, 80), width=3)
        d.line([x, y - r * 2, x, y + r * 2], fill=(255, 80, 80), width=3)
    if state.get("box_px"):
        x0, y0, x1, y1 = state["box_px"]
        d.rectangle([x0, y0, x1, y1], outline=(255, 80, 80), width=max(3, w // 320))
    out = str(Path(state["frame"]).with_name(Path(state["frame"]).stem + "-kotak.png"))
    img.save(out)
    return out


def klik_frame(state, evt: gr.SelectData):
    """Dua klik di frame contoh = kotak facecam. Klik ke-3 mulai ulang."""
    if not state or not state.get("frame"):
        raise gr.Error("Ambil frame contoh dulu sebelum klik.")
    x, y = evt.index
    width, height = state["size"]
    if state.get("p1") is None or state.get("box_px") is not None:
        state = {**state, "p1": (x, y), "box_px": None}
        return _gambar_kotak(state), state, gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), \
            "Sudut pertama tercatat. Sekarang klik sudut kanan-bawah kotak facecam."
    x0, y0 = state["p1"]
    box = (min(x0, x), min(y0, y), max(x0, x), max(y0, y))
    if box[2] - box[0] < 10 or box[3] - box[1] < 10:
        return _gambar_kotak(state), state, gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), \
            "Kotaknya terlalu kecil — klik sudut kedua lebih jauh dari sudut pertama."
    state = {**state, "box_px": box}
    fx = box[0] / width
    fy = box[1] / height
    fw = (box[2] - box[0]) / width
    fh = (box[3] - box[1]) / height
    return _gambar_kotak(state), state, fx, fy, fw, fh, "visual", \
        f"Kotak facecam terpilih: x={fx:.3f}, y={fy:.3f}, w={fw:.3f}, h={fh:.3f}. " \
        "Mode facecam otomatis pindah ke visual — tinggal klik Proses. Klik lagi di gambar untuk menggambar ulang."


def reset_kotak(state):
    if not state or not state.get("frame"):
        return gr.update(), state, "Belum ada frame contoh."
    state = {**state, "p1": None, "box_px": None}
    return state["frame"], state, "Kotak dihapus. Klik dua sudut di gambar untuk memilih ulang."


def analisis(video_path, num, klip_mode, manual_text, facecam_mode, fx, fy, fw, fh, fit_mode, top_ratio, model, lang, pakai_subs, progress=gr.Progress()):
    """Langkah 1: tentukan facecam, cari momen seru, transkrip. Hasil
    transkrip per klip ditampilkan sebagai teks yang BISA DIEDIT."""
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

    if klip_mode == "manual":
        progress(0.2, desc="Membaca rentang waktu pilihanmu...")
        try:
            moments = parse_ranges(manual_text or "", duration=_probe_duration(str(src)) or None)
        except ValueError as e:
            raise gr.Error(f"Rentang manual bermasalah: {e}") from None
        if not moments:
            raise gr.Error("Isi dulu rentang waktunya, satu per baris. Contoh: 1:23 - 1:45")
        if len(moments) > MAX_CLIPS:
            raise gr.Error(f"Maksimal {MAX_CLIPS} rentang sekali proses (kamu isi {len(moments)}).")
    else:
        progress(0.2, desc="Menganalisis suara untuk momen seru...")
        samples = extract_audio_samples(str(src))
        moments = find_highlights(samples, num_clips=int(num))
        if not moments:
            raise gr.Error("Tidak ada momen seru yang ditemukan di video ini.")

    words = []
    if pakai_subs:
        progress(0.5, desc="Mentranskrip omongan (Whisper)...")
        words = transcribe_words(str(src), model_size=model, language=lang or None)

    state = {
        "src": str(src), "box": box, "moments": moments,
        "words": words, "out_dir": str(out_dir), "size": (width, height),
        "fit_mode": fit_mode, "top_ratio": float(top_ratio) if top_ratio else None,
    }
    updates = [state]
    for i in range(MAX_CLIPS):
        if i < len(moments):
            m = moments[i]
            teks = " ".join(w["text"] for w in clip_words(words, m["start"], m["end"])) if words else ""
            updates.append(gr.update(
                visible=True, value=teks,
                label=f"Transkrip klip {i + 1} ({m['start']:.0f}s–{m['end']:.0f}s) — boleh diedit",
            ))
        else:
            updates.append(gr.update(visible=False, value=""))
    if pakai_subs:
        status = (f"Analisis selesai: {len(moments)} momen ditemukan, transkrip terisi di bawah. "
                  "Periksa & betulkan teksnya kalau ada kata yang salah dengar, lalu klik Render klip.")
    else:
        status = (f"Analisis selesai: {len(moments)} momen ditemukan (tanpa subtitle). "
                  "Klik Render klip untuk membuat videonya.")
    updates.append(status)
    return updates


def render(state, *teks_klip, progress=gr.Progress()):
    """Langkah 2: render klip memakai teks transkrip hasil editan."""
    if not state:
        raise gr.Error("Klik 'Analisis + transkrip' dulu sebelum render.")
    src = state["src"]
    out_dir = Path(state["out_dir"])
    box = state["box"]
    moments = state["moments"]
    words = state["words"]
    width, height = state["size"]

    sub_y = panel_height(width, height, state.get("top_ratio")) + 60
    hasil, thumbs = [], []
    for i, m in enumerate(moments, 1):
        progress(0.1 + 0.85 * i / len(moments), desc=f"Merender klip {i} dari {len(moments)}...")
        ass_path = None
        if words or (i - 1 < len(teks_klip) and teks_klip[i - 1].strip()):
            edited = teks_klip[i - 1] if i - 1 < len(teks_klip) else ""
            timed = retime_edited_words(words, edited, m["start"], m["end"])
            if timed:
                ass_path = str(out_dir / f"klip-{i:02d}.ass")
                words_to_ass(timed, m["start"], m["end"], ass_path, pos_y=sub_y)
        out_path = str(out_dir / f"klip-{i:02d}.mp4")
        render_clip(src, m["start"], m["end"], box, ass_path, out_path,
                    fit_mode=state.get("fit_mode", "crop"), top_ratio=state.get("top_ratio"))
        hasil.append(out_path)
        thumb = _thumbnail(out_path, min(3.0, (m["end"] - m["start"]) / 2), str(out_dir / f"klip-{i:02d}.jpg"))
        if thumb:
            thumbs.append((thumb, f"Klip {i}: {m['start']:.0f}s - {m['end']:.0f}s"))
    ringkasan = f"Selesai: {len(hasil)} klip dari {Path(src).name} (facecam di {box}). Tersimpan juga di folder {out_dir}/"
    return hasil, thumbs, ringkasan


with gr.Blocks(title="Auto Clipper") as demo:
    gr.Markdown("# ✂️ Auto Clipper\nPotong momen seru dari video stream jadi klip vertikal 9:16 — footage di atas, facecam di bawah, subtitle kata per kata.")
    with gr.Row():
        with gr.Column():
            video_in = gr.Video(label="Video stream sumber", sources=["upload"])
            klip_mode = gr.Radio(
                [("Otomatis — deteksi momen seru", "otomatis"), ("Manual — aku pilih sendiri bagiannya", "manual")],
                value="otomatis", label="Mode klip",
            )
            num = gr.Slider(1, 10, value=5, step=1, label="Jumlah klip (mode otomatis)")
            manual_text = gr.Textbox(
                label="Rentang manual — satu per baris: mulai - selesai (detik atau m:ss)",
                placeholder="1:23 - 1:45\n3:02 - 3:40",
                lines=3,
            )
            facecam_mode = gr.Radio(["auto", "manual", "visual"], value="auto", label="Posisi facecam")
            with gr.Row():
                fx = gr.Number(value=0.78, label="x (manual)")
                fy = gr.Number(value=0.72, label="y (manual)")
                fw = gr.Number(value=0.20, label="w (manual)")
                fh = gr.Number(value=0.26, label="h (manual)")
            gr.Markdown("**Pilih kotak facecam visual:** upload video → klik *Ambil frame contoh* → klik dua sudut kotak wajah di gambar (kiri-atas lalu kanan-bawah). Angka x/y/w/h di atas terisi otomatis.")
            with gr.Row():
                tombol_frame = gr.Button("🖼️ Ambil frame contoh")
                tombol_reset = gr.Button("↺ Reset kotak")
            frame_img = gr.Image(label="Frame contoh — klik dua sudut kotak facecam", type="filepath", interactive=False)
            kotak_state = gr.State(None)
            model = gr.Dropdown(["tiny", "base", "small", "medium", "large-v3"], value="small", label="Model Whisper")
            lang = gr.Textbox(value="id", label="Bahasa transkrip (id/en/...)")
            fit_mode = gr.Dropdown(
                [("Isi penuh — potong sisi (crop)", "crop"),
                 ("Utuh — latar blur", "fit-blur"),
                 ("Utuh — latar hitam", "fit-hitam")],
                value="crop", label="Mode tampilan footage",
            )
            top_ratio = gr.Slider(0, 0.75, value=0, step=0.01, label="Tinggi panel footage (0 = otomatis proporsional; 0.5 = setengah layar)")
            pakai_subs = gr.Checkbox(value=True, label="Pakai subtitle")
            tombol = gr.Button("1️⃣ Analisis + transkrip", variant="primary")
            analisis_state = gr.State(None)
            gr.Markdown("**Edit transkrip (opsional):** setelah analisis, teks tiap klip muncul di bawah ini. Betulkan kata yang salah dengar, hapus kata, atau tambah kata — timing subtitle menyesuaikan otomatis saat render.")
            teks_klip = [
                gr.Textbox(label=f"Transkrip klip {i + 1}", visible=False, lines=2, max_lines=4)
                for i in range(MAX_CLIPS)
            ]
            tombol_render = gr.Button("2️⃣ Render klip", variant="primary")
        with gr.Column():
            files_out = gr.File(label="Klip hasil (klik untuk unduh)", file_count="multiple")
            gallery_out = gr.Gallery(label="Intip thumbnail klip", columns=3)
            status = gr.Textbox(label="Status", interactive=False)
    tombol.click(
        analisis,
        inputs=[video_in, num, klip_mode, manual_text, facecam_mode, fx, fy, fw, fh, fit_mode, top_ratio, model, lang, pakai_subs],
        outputs=[analisis_state, *teks_klip, status],
    )
    tombol_render.click(
        render,
        inputs=[analisis_state, *teks_klip],
        outputs=[files_out, gallery_out, status],
    )
    tombol_frame.click(
        ambil_frame,
        inputs=[video_in],
        outputs=[frame_img, kotak_state, status],
    )
    frame_img.select(
        klik_frame,
        inputs=[kotak_state],
        outputs=[frame_img, kotak_state, fx, fy, fw, fh, facecam_mode, status],
    )
    tombol_reset.click(
        reset_kotak,
        inputs=[kotak_state],
        outputs=[frame_img, kotak_state, status],
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lan", action="store_true", help="Izinkan akses dari perangkat lain di Wi-Fi yang sama")
    args = ap.parse_args()
    demo.launch(server_name="0.0.0.0" if args.lan else "127.0.0.1", server_port=7860)
