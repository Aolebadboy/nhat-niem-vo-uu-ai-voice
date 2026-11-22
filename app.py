import streamlit as st
import requests, tempfile, subprocess
from pathlib import Path
import imageio_ffmpeg

st.set_page_config(
    page_title="Nhất Niệm Vô Ưu AI Voice",
    page_icon="🪷",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Mobile-first layout: large controls, single column, no wide tables.
st.markdown("""
<style>
    .block-container {max-width: 760px; padding: 1rem 1rem 3rem; }
    h1 {font-size: clamp(1.55rem, 6vw, 2.2rem) !important; line-height:1.2;}
    h2, h3 {font-size: 1.2rem !important;}
    div.stButton > button, div.stDownloadButton > button {
        width:100%; min-height:3.2rem; border-radius:14px;
        font-size:1.05rem; font-weight:700;
    }
    textarea {font-size:16px !important; line-height:1.55 !important;}
    input {font-size:16px !important;}
    [data-testid="stFileUploader"] {width:100%;}
    .mobile-note {padding:12px 14px; border-radius:12px; background:rgba(128,128,128,.12);}
    footer {visibility:hidden;}
</style>
""", unsafe_allow_html=True)

st.title("🪷 NHẤT NIỆM VÔ ƯU")
st.subheader("AI VOICE – Tạo giọng đọc & ghép nhạc")
st.markdown('<div class="mobile-note">Dành cho điện thoại: dán kịch bản, chọn giọng, thêm nhạc nền và xuất một file MP3 hoàn chỉnh.</div>', unsafe_allow_html=True)

with st.expander("⚙️ Cài đặt giọng đọc", expanded=True):
    api_key = st.text_input("API Key", type="password", help="Nhập khóa API của nhà cung cấp TTS. Không gửi khóa cho người khác.")
    voice_label = st.selectbox("Giọng đọc", ["Nam – Triệu Dương", "Nữ – Mai"])
    voice = "Trieu Duong" if voice_label.startswith("Nam") else "Mai"
    model_label = st.selectbox("Chất lượng giọng", ["Tiêu chuẩn", "HD"])
    model = "larouter-tts" if model_label == "Tiêu chuẩn" else "larouter-tts-hd"
    bg_volume = st.slider("Âm lượng nhạc nền", 0, 40, 12, format="%d%%")
    fade = st.checkbox("Giảm âm lượng nhạc ở cuối", value=True)

st.header("1. Kịch bản")
script = st.text_area(
    "Dán toàn bộ nội dung tại đây",
    height=280,
    placeholder="Ví dụ: Con hãy bình tâm lắng nghe lời Phật dạy..."
)
st.caption(f"Độ dài hiện tại: {len(script):,} ký tự. Kịch bản sẽ tự chia đoạn để gửi xử lý.")

st.header("2. Nhạc nền")
music = st.file_uploader(
    "Chọn nhạc thiền / tiếng chuông chùa từ điện thoại",
    type=["mp3", "wav", "m4a", "aac", "ogg"],
    help="Chỉ sử dụng âm thanh bạn có quyền sử dụng, đặc biệt nếu đăng video kiếm tiền."
)
if music:
    st.success(f"Đã chọn: {music.name}")

def split_text(text, limit=8500):
    paras = [p.strip() for p in text.replace("\r\n", "\n").split("\n") if p.strip()]
    chunks, current = [], ""
    for para in paras:
        pieces = []
        rest = para
        while len(rest) > limit:
            cut = max(rest.rfind(mark, 0, limit) for mark in [". ", "! ", "? ", "; ", ", "])
            if cut < limit // 2:
                cut = limit
            else:
                cut += 1
            pieces.append(rest[:cut].strip())
            rest = rest[cut:].strip()
        if rest:
            pieces.append(rest)
        for piece in pieces:
            candidate = (current + "\n\n" + piece).strip()
            if current and len(candidate) > limit:
                chunks.append(current)
                current = piece
            else:
                current = candidate
    if current:
        chunks.append(current)
    return chunks

def ffmpeg_path():
    return imageio_ffmpeg.get_ffmpeg_exe()

def run_ffmpeg(args):
    p = subprocess.run([ffmpeg_path(), "-y"] + args, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError((p.stderr or "Lỗi xử lý âm thanh")[-1800:])

if st.button("🎙️ TẠO GIỌNG ĐỌC MP3", type="primary", use_container_width=True):
    if not api_key.strip():
        st.error("Vui lòng nhập API Key trong phần Cài đặt giọng đọc.")
    elif not script.strip():
        st.error("Vui lòng dán kịch bản trước khi tạo.")
    else:
        chunks = split_text(script)
        st.info(f"Kịch bản gồm {len(chunks)} đoạn. Vui lòng giữ trang web mở đến khi hoàn tất.")
        progress = st.progress(0)
        status = st.empty()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                part_files = []
                for i, chunk in enumerate(chunks):
                    status.write(f"Đang tạo giọng đọc: đoạn {i+1}/{len(chunks)}")
                    response = requests.post(
                        "https://i-larouter.lapage.vn/v1/audio/speech",
                        headers={
                            "Authorization": f"Bearer {api_key.strip()}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": model,
                            "voice": voice,
                            "input": chunk,
                            "response_format": "mp3"
                        },
                        timeout=300
                    )
                    if not response.ok:
                        raise RuntimeError(
                            f"Lỗi từ dịch vụ ở đoạn {i+1}: HTTP {response.status_code}. "
                            f"{response.text[:700]}"
                        )
                    part = tmp / f"part_{i:04d}.mp3"
                    part.write_bytes(response.content)
                    part_files.append(part)
                    progress.progress((i + 1) / (len(chunks) + 1))

                normalized = []
                for i, part in enumerate(part_files):
                    out = tmp / f"norm_{i:04d}.mp3"
                    run_ffmpeg(["-i", str(part), "-ar", "44100", "-ac", "2", "-b:a", "192k", str(out)])
                    normalized.append(out)

                listing = tmp / "concat.txt"
                listing.write_text(
                    "\n".join("file '" + p.as_posix() + "'" for p in normalized),
                    encoding="utf-8"
                )
                voice_file = tmp / "voice.mp3"
                run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(voice_file)])

                final_file = tmp / "nhat_niem_vo_uu.mp3"
                if music is not None:
                    music_path = tmp / ("background" + Path(music.name).suffix.lower())
                    music_path.write_bytes(music.getvalue())
                    filters = (
                        f"[1:a]volume={bg_volume/100.0}[bg];"
                        "[0:a][bg]amix=inputs=2:duration=first:dropout_transition=3[mix]"
                    )
                    if fade:
                        filters += ";[mix]afade=t=out:st=0:d=5[out]"
                        output_label = "[out]"
                    else:
                        output_label = "[mix]"
                    run_ffmpeg([
                        "-i", str(voice_file), "-stream_loop", "-1", "-i", str(music_path),
                        "-filter_complex", filters, "-map", output_label,
                        "-c:a", "libmp3lame", "-b:a", "192k", "-shortest", str(final_file)
                    ])
                else:
                    final_file = voice_file

                result = final_file.read_bytes()
                progress.progress(1.0)
                status.success("Đã tạo xong! Nghe thử bên dưới rồi tải về điện thoại.")
                st.audio(result, format="audio/mp3")
                st.download_button(
                    "⬇️ TẢI MP3 VỀ ĐIỆN THOẠI",
                    data=result,
                    file_name="nhat_niem_vo_uu.mp3",
                    mime="audio/mpeg",
                    use_container_width=True
                )
        except Exception as exc:
            st.error(f"Chưa tạo được âm thanh: {exc}")
            st.caption("Hãy kiểm tra API Key, kết nối mạng và hạn mức của tài khoản TTS.")

st.divider()
st.caption("Lưu ý: Đây là website cần được triển khai lên máy chủ mới mở được bằng điện thoại. Tự chia đoạn giúp nhập kịch bản dài, nhưng không thể vượt hạn mức hoặc chi phí của nhà cung cấp giọng đọc.")
