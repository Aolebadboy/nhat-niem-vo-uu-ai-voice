import re
import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg
import requests
import streamlit as st

API_URL = "https://i-larouter.lapage.vn/v1/audio/speech"
CHUNK_LIMIT = 9000

st.set_page_config(page_title="Nhất Niệm Vô Ưu AI Voice", page_icon="🪷", layout="centered")
st.markdown(""" <style> .block-container{max-width:780px;padding:1rem 1rem 3rem} h1{font-size:clamp(1.55rem,6vw,2.2rem)!important} textarea,input{font-size:16px!important} div.stButton>button,div.stDownloadButton>button{width:100%;min-height:3.1rem;border-radius:13px;font-weight:700} footer{visibility:hidden} </style> """, unsafe_allow_html=True)

st.title("🪷 NHẤT NIỆM VÔ ƯU")
st.subheader("AI VOICE · Tạo giọng đọc MP3")
st.info("Dán kịch bản, chọn giọng, thêm nhạc nền tùy chọn và xuất một file MP3 hoàn chỉnh.")

with st.expander("⚙️ Cài đặt giọng đọc", expanded=True):
    api_key = st.text_input("LaRouter API Key", type="password",
                            help="Khóa chỉ dùng trong phiên hiện tại. Không đưa API Key lên GitHub.")
    voice_label = st.selectbox("Giọng đọc", [
        "Nam – Triệu Dương", "Nữ – Mai", "Nữ – Như",
        "Nam – Thế Hào", "Nam – Minh Trung"
    ])
    voices = {
        "Nam – Triệu Dương": "Trieu Duong", "Nữ – Mai": "Mai",
        "Nữ – Như": "Như", "Nam – Thế Hào": "Thế Hào",
        "Nam – Minh Trung": "Minh Trung"
    }
    voice = voices[voice_label]
    model_label = st.selectbox("Chất lượng", ["Tiêu chuẩn", "HD"])
    model = "larouter-tts" if model_label == "Tiêu chuẩn" else "larouter-tts-hd"

st.header("1. Kịch bản")
script = st.text_area("Dán toàn bộ nội dung tại đây", height=300,
                      placeholder="Ví dụ: Con hãy bình tâm lắng nghe lời Phật dạy...")
st.caption(f"Độ dài: {len(script):,} ký tự.")

st.header("2. Nhạc nền (không bắt buộc)")
music = st.file_uploader("Chọn nhạc thiền / tiếng chuông chùa",
                         type=["mp3", "wav", "m4a", "aac", "ogg"])
c1, c2 = st.columns(2)
with c1:
    bg_volume = st.slider("Âm lượng nhạc (%)", 0, 50, 12)
with c2:
    fade_seconds = st.slider("Giảm nhạc cuối bài (giây)", 0, 15, 5)


def split_text(text, limit=CHUNK_LIMIT):
    text = text.strip()
    chunks = []
    while len(text) > limit:
        window = text[:limit]
        cut = -1
        for mark in ["\n\n", ". ", "! ", "? ", "\n", "; ", ", ", " "]:
            pos = window.rfind(mark)
            if pos > limit * 0.55:
                cut = max(cut, pos + len(mark))
        if cut < 1:
            cut = limit
        part = text[:cut].strip()
        if part:
            chunks.append(part)
        text = text[cut:].strip()
    if text:
        chunks.append(text)
    return chunks


def ffmpeg(args):
    proc = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-y"] + args,
        capture_output=True, text=True
    )
    if proc.returncode:
        raise RuntimeError((proc.stderr or "Lỗi FFmpeg")[-1600:])
    return proc


def duration_seconds(path):
    proc = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(path), "-f", "null", "-"],
        capture_output=True, text=True
    )
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", proc.stderr or "")
    if not m:
        raise RuntimeError("Không đọc được thời lượng âm thanh.")
    h, minute, sec = m.groups()
    return int(h) * 3600 + int(minute) * 60 + float(sec)


def tts_request(text, key):
    try:
        r = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {key.strip()}",
                     "Content-Type": "application/json"},
            json={"model": model, "voice": voice, "input": text, "response_format": "mp3"},
            timeout=(30, 300)
        )
    except requests.RequestException as e:
        raise RuntimeError(f"Không kết nối được LaRouter: {e}") from e

    if not r.ok:
        detail = (r.text or "")[:800]
        if r.status_code == 401:
            raise RuntimeError("API Key không hợp lệ hoặc chưa được cấp quyền (401).")
        if r.status_code == 429:
            raise RuntimeError("Đã chạm giới hạn hoặc hết hạn mức API (429). Hãy kiểm tra tài khoản.")
        raise RuntimeError(f"LaRouter HTTP {r.status_code}: {detail}")
    if len(r.content) < 500 or "json" in r.headers.get("content-type", "").lower():
        raise RuntimeError("Phản hồi không phải file âm thanh hợp lệ. Kiểm tra model và quyền API.")
    return r.content


def create_mp3():
    if not api_key.strip():
        st.error("Hãy nhập LaRouter API Key.")
        return
    if not script.strip():
        st.error("Hãy nhập kịch bản.")
        return

    chunks = split_text(script)
    rate = 0.20 if model == "larouter-tts-hd" else 0.10
    st.info(f"Kịch bản gồm {len(chunks)} đoạn. Chi phí ước tính khoảng ${len(script)/1000*rate:.3f}; "
            "số thực tế tùy mức tính phí của LaRouter.")
    bar, status = st.progress(0), st.empty()

    try:
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            wav_parts = []

            for i, chunk in enumerate(chunks):
                status.write(f"Đang tạo giọng đọc: đoạn {i+1}/{len(chunks)}")
                raw = tts_request(chunk, api_key)
                mp3 = work / f"part_{i:04d}.mp3"
                wav = work / f"part_{i:04d}.wav"
                mp3.write_bytes(raw)
                ffmpeg(["-i", str(mp3), "-ar", "44100", "-ac", "2",
                        "-c:a", "pcm_s16le", str(wav)])
                wav_parts.append(wav)
                bar.progress((i + 1) / (len(chunks) + 2))

            listing = work / "concat.txt"
            listing.write_text(
                "\n".join("file '" + p.as_posix() + "'" for p in wav_parts),
                encoding="utf-8"
            )
            voice_wav = work / "voice.wav"
            ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listing),
                    "-c:a", "pcm_s16le", str(voice_wav)])

            final_mp3 = work / "nhat_niem_vo_uu.mp3"
            if music is not None and bg_volume > 0:
                music_path = work / ("background" + Path(music.name).suffix.lower())
                music_path.write_bytes(music.getvalue())
                total = duration_seconds(voice_wav)
                bg_filter = f"[1:a]volume={bg_volume/100:.3f}"
                if fade_seconds > 0 and total > 0:
                    fade_len = min(float(fade_seconds), total)
                    fade_start = max(0.0, total - fade_len)
                    bg_filter += f",afade=t=out:st={fade_start:.3f}:d={fade_len:.3f}"
                filters = bg_filter + "[bg];[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[mix]"
                ffmpeg(["-i", str(voice_wav), "-stream_loop", "-1", "-i", str(music_path),
                        "-filter_complex", filters, "-map", "[mix]",
                        "-c:a", "libmp3lame", "-b:a", "192k", "-t", f"{total:.3f}",
                        str(final_mp3)])
            else:
                ffmpeg(["-i", str(voice_wav), "-c:a", "libmp3lame",
                        "-b:a", "192k", str(final_mp3)])

            data = final_mp3.read_bytes()
            bar.progress(1.0)
            status.success("Đã tạo xong! Nghe thử và tải MP3 bên dưới.")
            st.audio(data, format="audio/mp3")
            st.download_button("⬇️ TẢI MP3 VỀ ĐIỆN THOẠI", data=data,
                               file_name="nhat_niem_vo_uu.mp3",
                               mime="audio/mpeg", use_container_width=True)
    except Exception as e:
        status.empty()
        st.error(f"Tạo âm thanh chưa thành công: {e}")
        st.caption("Kiểm tra API Key, hạn mức LaRouter, mạng và model/giọng đọc.")


if st.button("🎙️ TẠO GIỌNG ĐỌC MP3", type="primary", use_container_width=True):
    create_mp3()

st.divider()
st.caption("Tự chia đoạn giúp gửi kịch bản dài hơn giới hạn mỗi yêu cầu, nhưng không vượt hạn mức hoặc chi phí TTS. "
           "Chỉ dùng nhạc nền bạn có quyền sử dụng. Website cần được triển khai lên máy chủ Streamlit.")