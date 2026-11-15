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
