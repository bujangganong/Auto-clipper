# Auto Clipper

Potong otomatis momen paling seru dari video stream panjang, lalu render jadi klip vertikal **9:16 (1080×1920)** siap Shorts/TikTok:

- **Footage utama di atas, facecam di bawah** — seperti format klip-klip streamer populer
- **Subtitle otomatis kata per kata** — huruf kapital besar, putih tebal garis hitam, dari transkrip Whisper
- **Deteksi momen seru** dari lonjakan energi suara (teriakan, ketawa, momen kaget)

## Cara kerja

1. Audio video dianalisis: jendela suara yang menonjol dibanding sekitarnya dianggap momen seru (`highlights.py`).
2. Omongan ditranskrip per kata dengan [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (`subtitles.py`).
3. Tiap momen dirender dengan FFmpeg: facecam dipotong dari kotaknya, disusun vertikal, subtitle dibakar ke video (`layout.py`).

## Persiapan (Windows)

```bat
winget install Gyan.FFmpeg
conda create -n auto-clipper python=3.11 -y
conda activate auto-clipper
pip install -r requirements.txt
```

GPU NVIDIA (CUDA) dipakai otomatis oleh faster-whisper bila tersedia; tanpa GPU tetap jalan di CPU (pilih model Whisper yang lebih kecil, mis. `base`).

## Pakai

```bat
python clipper.py stream.mp4 --facecam auto --num 5
```

Opsi penting:

| Opsi | Arti |
|---|---|
| `--facecam auto` | Tebak posisi facecam dari deteksi wajah |
| `--facecam 0.78,0.72,0.20,0.26` | Kotak facecam manual `x,y,w,h` relatif 0–1 (pojok kanan bawah pada contoh ini) |
| `--num 5` | Jumlah klip yang dibuat |
| `--model small` | Model Whisper: `tiny`/`base`/`small`/`medium`/`large-v3` |
| `--lang id` | Bahasa transkrip (`id`, `en`, ...) |
| `--out clips` | Folder hasil |
| `--no-subs` | Lewati subtitle |

Hasil: `clips/klip-01.mp4`, `klip-02.mp4`, ... beserta file `.ass` subtitlenya.

## Catatan

- Kualitas deteksi momen bergantung pada karakter video: stream dengan reaksi vokal yang jelas memberi hasil terbaik.
- Kotak facecam manual selalu lebih akurat daripada tebakan otomatis — ukur sekali dari layout OBS kamu, pakai seterusnya.
- Klip dari video orang lain tunduk pada hak cipta pemiliknya; pakai untuk videomu sendiri atau dengan izin.

## Lisensi

MIT
