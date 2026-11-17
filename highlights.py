"""Deteksi momen seru dari lonjakan energi suara.

Prinsipnya: momen seru di stream (teriakan, ketawa, kaget) hampir selalu
ditandai volume yang melonjak dibanding rata-rata video. Kita hitung RMS
audio per jendela pendek, cari puncaknya, lalu potong segmen di sekitarnya.
"""

from __future__ import annotations

import subprocess
import numpy as np


def extract_audio_samples(video_path: str, sample_rate: int = 16000) -> np.ndarray:
    """Ambil audio mono 16 kHz dari video lewat ffmpeg, kembalikan float32 [-1, 1]."""
    cmd = [
        "ffmpeg", "-v", "error", "-i", video_path,
        "-vn", "-ac", "1", "-ar", str(sample_rate), "-f", "f32le", "-",
    ]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


def _rms_curve(samples: np.ndarray, sample_rate: int, window_sec: float = 0.5) -> np.ndarray:
    """RMS per jendela window_sec detik."""
    win = int(sample_rate * window_sec)
    n = len(samples) // win
    if n == 0:
        return np.zeros(0)
    frames = samples[: n * win].reshape(n, win)
    return np.sqrt(np.mean(frames ** 2, axis=1) + 1e-12)


def parse_time(teks: str) -> float:
    """Ubah teks waktu jadi detik: '83', '1:23', '1:02:30', '1:23.5'."""
    teks = teks.strip()
    if not teks:
        raise ValueError("waktu kosong")
    parts = teks.split(":")
    if len(parts) > 3:
        raise ValueError(f"format waktu tidak dikenal: {teks!r}")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        raise ValueError(f"format waktu tidak dikenal: {teks!r}") from None
    total = 0.0
    for n in nums:
        total = total * 60 + n
    return total


def parse_ranges(teks: str, duration: float | None = None) -> list[dict]:
    """Ubah daftar rentang manual jadi segmen [{start, end, score}].

    Format: satu rentang per baris (koma juga boleh), 'mulai - selesai',
    waktu dalam detik atau mm:ss / hh:mm:ss. Contoh: '1:23 - 1:45'.
    """
    moments = []
    for chunk in teks.replace(",", "\n").splitlines():
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" not in chunk:
            raise ValueError(f"rentang harus 'mulai - selesai', dapat: {chunk!r}")
        a, b = chunk.split("-", 1)
        start, end = parse_time(a), parse_time(b)
        if end <= start:
            raise ValueError(f"selesai harus lebih besar dari mulai: {chunk!r}")
        if duration is not None:
            start = max(0.0, min(start, duration))
            end = max(0.0, min(end, duration))
            if end <= start:
                continue
        moments.append({"start": start, "end": end, "score": 0.0})
    return sorted(moments, key=lambda m: m["start"])


def find_highlights(
    samples: np.ndarray,
    sample_rate: int = 16000,
    num_clips: int = 5,
    pre_sec: float = 8.0,
    post_sec: float = 22.0,
    window_sec: float = 0.5,
) -> list[dict]:
    """Cari segmen paling seru. Hasil: list {start, end, score} terurut waktu."""
    rms = _rms_curve(samples, sample_rate, window_sec)
    if len(rms) == 0:
        return []
    duration = len(samples) / sample_rate

    # Skor lokal: seberapa menonjol jendela ini dibanding sekitarnya (+-15 detik)
    ctx = int(15 / window_sec)
    kernel = np.ones(2 * ctx + 1)
    local_mean = np.convolve(np.pad(rms, ctx, mode="edge"), kernel, mode="valid") / (2 * ctx + 1)
    score_curve = rms / (local_mean + 1e-6) * np.sqrt(rms + 1e-9)

    threshold = np.percentile(score_curve, 90)
    candidates = []
    order = np.argsort(score_curve)[::-1]
    taken: list[tuple[float, float]] = []
    for idx in order:
        if score_curve[idx] < threshold:
            break
        t = idx * window_sec
        start = max(0.0, t - pre_sec)
        end = min(duration, t + post_sec)
        if any(not (end < s or start > e) for s, e in taken):
            continue  # tumpang tindih dengan segmen yang sudah dipilih
        taken.append((start, end))
        candidates.append({"start": start, "end": end, "score": float(score_curve[idx])})
        if len(candidates) >= num_clips:
            break
    return sorted(candidates, key=lambda c: c["start"])
