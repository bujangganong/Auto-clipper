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

## Pakai — tampilan web (seperti FaceFusion)

```bat
conda activate auto-clipper
python app.py
```

Lalu buka **http://127.0.0.1:7860** di browser: seret file video, atur jumlah klip & posisi facecam, klik **Proses**. Klip hasil bisa diunduh dari halaman yang sama, lengkap dengan galeri thumbnail buat mengintip isinya.

**Posisi facecam visual:** mode `visual` — klik **Ambil frame contoh**, lalu klik dua sudut kotak wajah di gambar contoh (kiri-atas, lalu kanan-bawah). Kotaknya tergambar di gambar dan angka `x/y/w/h` terisi otomatis; klik lagi untuk menggambar ulang. Lebih gampang daripada menebak angka manual.

**Edit transkrip:** tampilan web bekerja dua langkah. **1. Analisis + transkrip** mencari momen seru dan mengisi teks transkrip tiap klip — teks itu **bisa diedit** (betulkan kata yang salah dengar, hapus, atau tambah kata). **2. Render klip** membuat video memakai teks hasil editan; timing kata-per-kata menyesuaikan otomatis (kata yang tidak diubah mempertahankan timing Whisper aslinya).

**Kustomisasi panel footage:** pilihan *Mode tampilan footage* — `crop` (isi penuh panel, sisi berlebih dipotong), `fit-blur` (footage tampil utuh, ruang kosong diisi latar blur dari footage itu sendiri), atau `fit-hitam` (footage utuh berlatar hitam). Slider *Tinggi panel footage* mengatur porsi layar untuk footage (0 = proporsional otomatis; 0.5 = setengah layar, facecam mengisi sisanya). Di terminal: `--fit` dan `--top-ratio`.

Tambahkan `--lan` (`python app.py --lan`) kalau mau membuka halamannya dari HP selama laptop menyala di Wi-Fi yang sama.

## Pakai — terminal

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
