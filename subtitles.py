"""Transkrip Whisper per kata -> subtitle ASS gaya klip TikTok/Shorts.

Gaya: satu kata (atau frasa pendek) tampil besar di tengah layar,
huruf kapital, putih tebal dengan garis tepi hitam — seperti klip-klip
streamer yang jadi referensi.
"""

from __future__ import annotations

import re


def transcribe_words(video_path: str, model_size: str = "small", language: str | None = None) -> list[dict]:
    """Transkrip video dengan faster-whisper. Hasil: list {start, end, text} per kata (detik absolut)."""
    from faster_whisper import WhisperModel

    try:
        model = WhisperModel(model_size, device="cuda", compute_type="float16")
    except Exception:
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(video_path, language=language, word_timestamps=True)
    words = []
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append({"start": w.start, "end": w.end, "text": text})
    return words


def clip_words(words: list[dict], clip_start: float, clip_end: float) -> list[dict]:
    """Kata-kata yang jatuh di dalam rentang klip [clip_start, clip_end]."""
    return [w for w in words if not (w["end"] < clip_start or w["start"] > clip_end)]


def retime_edited_words(words: list[dict], edited_text: str, clip_start: float, clip_end: float) -> list[dict]:
    """Susun ulang timing kata setelah teks transkrip diedit pemakai.

    Kata yang tidak berubah mempertahankan timestamp Whisper aslinya.
    Kata yang diganti/disispkan mendapat jatah waktu dari rentang kata
    asli di sekitarnya, jadi gaya subtitle kata-per-kata tetap sinkron.
    Kata yang dihapus hilang. Kalau aslinya tidak ada kata sama sekali,
    teks editan disebar merata di sepanjang klip.
    """
    import difflib

    orig = clip_words(words, clip_start, clip_end)
    tokens = edited_text.split()
    if not tokens:
        return []
    if not orig:
        dur = max(0.1, clip_end - clip_start)
        step = dur / len(tokens)
        return [
            {"start": clip_start + i * step, "end": clip_start + (i + 1) * step, "text": t}
            for i, t in enumerate(tokens)
        ]
    orig_tokens = [w["text"] for w in orig]
    sm = difflib.SequenceMatcher(
        a=[t.lower() for t in orig_tokens],
        b=[t.lower() for t in tokens],
        autojunk=False,
    )
    out: list[dict] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(j2 - j1):
                w = orig[i1 + k]
                out.append({"start": w["start"], "end": w["end"], "text": tokens[j1 + k]})
        elif tag in ("replace", "insert"):
            if tag == "replace" and i2 > i1:
                t_start = orig[i1]["start"]
                t_end = orig[i2 - 1]["end"]
            else:
                t_start = orig[i1 - 1]["end"] if i1 > 0 else clip_start
                t_end = orig[i2]["start"] if i2 < len(orig) else clip_end
            n = j2 - j1
            if t_end <= t_start:
                t_end = t_start + 0.12 * n
            step = (t_end - t_start) / n
            for k in range(n):
                s = t_start + k * step
                out.append({"start": s, "end": s + step, "text": tokens[j1 + k]})
        # "delete": kata asli dibuang, tidak diikutkan
    out.sort(key=lambda w: w["start"])
    return out


def _ass_time(sec: float) -> str:
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _escape(text: str) -> str:
    return text.replace("\\", "").replace("{", "").replace("}", "").strip()


def words_to_ass(
    words: list[dict],
    clip_start: float,
    clip_end: float,
    out_path: str,
    pos_y: int = 900,
    font_size: int = 120,
) -> str:
    """Tulis file .ass berisi kata-kata dalam rentang [clip_start, clip_end].

    Waktu digeser relatif terhadap awal klip. Setiap kata tampil sendiri
    (uppercase) di posisi tengah layar (x=540 pada kanvas 1080x1920).
    """
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Klip,Arial Black,{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,10,2,5,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for w in words:
        if w["end"] < clip_start or w["start"] > clip_end:
            continue
        start = max(0.0, w["start"] - clip_start)
        end = max(start + 0.12, w["end"] - clip_start)
        text = _escape(re.sub(r"\s+", " ", w["text"])).upper()
        if not text:
            continue
        lines.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Klip,,0,0,0,,"
            f"{{\\pos(540,{pos_y})}}{text}"
        )
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return out_path
