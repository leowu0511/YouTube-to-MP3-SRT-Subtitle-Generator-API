"""
YouTube to MP3 & SRT (Groq Whisper) Service
============================================
使用 FastAPI + yt-dlp + ffmpeg + Groq Whisper API：
1. 輸入 YouTube 網址轉換為 MP3 檔案下載。
2. 呼叫 Groq Whisper API 自動生成帶有時間軸的 .srt 字幕檔。
傳送完成後自動刪除伺服器上的所有暫存檔案。
"""

import json
import os
import re
import shutil
import tempfile
import unicodedata
from pathlib import Path
from urllib.parse import quote
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yt_dlp
import httpx
from dotenv import load_dotenv

# 載入 .env 變數
load_dotenv()

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="YouTube MP3 & SRT Subtitle Generator API",
    description="輸入 YouTube 網址，轉為 MP3 音訊或呼叫 Groq Whisper 生成帶時間軸的 SRT 字幕檔。",
    version="1.1.0",
)

# 暫存與快取目錄
TEMP_DIR = Path(tempfile.gettempdir()) / "yt_mp3_downloads"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

CACHE_DIR = Path("/app/srt_cache")
if not CACHE_DIR.parent.exists():
    CACHE_DIR = Path(tempfile.gettempdir()) / "yt_srt_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
YOUTUBE_URL_PATTERN = re.compile(
    r"^(https?://)?(www\.)?"
    r"(youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)"
    r"[\w\-]{11}"
)


def extract_video_id(url: str) -> Optional[str]:
    """從 YouTube 網址提取 11 字元的 video ID"""
    match = re.search(r"(?:v=|\/([0-9A-Za-z_-]{11}))([0-9A-Za-z_-]{11})?", url)
    if match:
        for g in match.groups():
            if g and len(g) == 11:
                return g
    return None


def get_cached_srt(video_id: str, language: Optional[str]) -> Optional[tuple[str, str]]:
    """從伺服器快取嘗試獲取 SRT 內容與影片標題 (title, srt_content)"""
    lang_key = language or "auto"
    cache_file = CACHE_DIR / f"{video_id}_{lang_key}.json"
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            return data.get("title", "subtitle"), data.get("srt_content", "")
        except Exception:
            pass
    return None


def save_srt_cache(video_id: str, language: Optional[str], title: str, srt_content: str) -> None:
    """將生成的 SRT 與影片標題永久保存至伺服器快取"""
    lang_key = language or "auto"
    cache_file = CACHE_DIR / f"{video_id}_{lang_key}.json"
    try:
        data = {
            "video_id": video_id,
            "language": lang_key,
            "title": title,
            "srt_content": srt_content,
        }
        cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[WARN] 儲存 SRT 快取失敗: {e}")


def is_valid_youtube_url(url: str) -> bool:
    """檢查是否為合法的 YouTube 網址。"""
    return bool(YOUTUBE_URL_PATTERN.match(url))


def sanitize_filename(name: str) -> str:
    """移除 / 替換檔名中不允許的特殊字元，保留完整的中文與 Unicode 字元。"""
    # 正規化 Unicode (NFC 避免組合字元散落)
    name = unicodedata.normalize("NFC", name)
    # 移除 Windows / Linux 不允許的檔名特殊字元 \ / * ? : " < > |
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    # 將連續空白替換為底線
    name = re.sub(r"\s+", "_", name.strip())
    # 限制長度
    if len(name) > 200:
        name = name[:200]
    return name or "subtitle"


def cleanup_directory(dirpath: str) -> None:
    """背景任務或失敗時：清除整個暫存子目錄。"""
    try:
        path = Path(dirpath)
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


def download_as_mp3(url: str, output_dir: Path) -> tuple[str, str, str]:
    """
    使用 yt-dlp + ffmpeg 下載 YouTube 音訊並轉為 MP3。
    回傳 (mp3_filepath, sanitized_filename, raw_title)
    """
    outtmpl = str(output_dir / "%(title)s.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        },
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios", "tv_embedded", "web_creator", "mweb"],
                "skip": ["hls", "dash"],
            }
        },
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    raw_title = info.get("title", "audio")
    sanitized = sanitize_filename(raw_title)

    # 搜尋 output_dir 內的 .mp3 檔案
    mp3_files = list(output_dir.glob("*.mp3"))
    if not mp3_files:
        raise FileNotFoundError("轉檔完成但找不到 MP3 檔案。")

    source = mp3_files[0]
    final_path = output_dir / f"{sanitized}.mp3"
    if source != final_path:
        source.rename(final_path)

    return str(final_path), f"{sanitized}.mp3", sanitized


def format_timestamp(seconds: float) -> str:
    """將秒數轉換為 SRT 時間軸格式 HH:MM:SS,mmm"""
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        seconds += 1
        millis = 0
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def verbose_json_to_srt(data: dict) -> str:
    """將 Groq Whisper verbose_json 回應轉為標準 .srt 字幕格式內容"""
    segments = data.get("segments", [])
    srt_blocks = []
    for idx, seg in enumerate(segments, 1):
        start_str = format_timestamp(seg.get("start", 0.0))
        end_str = format_timestamp(seg.get("end", 0.0))
        text = seg.get("text", "").strip()
        srt_blocks.append(f"{idx}\n{start_str} --> {end_str}\n{text}\n")
    return "\n".join(srt_blocks)


async def transcribe_with_groq(
    mp3_path: str,
    model: str = "whisper-large-v3",
    language: Optional[str] = None,
) -> str:
    """呼叫 Groq Whisper API (verbose_json) 進行語音轉文字，並轉換為帶時間軸的 SRT 字幕。"""
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="伺服器未設定 GROQ_API_KEY。請在 .env 檔案中填入您的 Groq API Key。",
        )

    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {api_key}"}

    # 檢查檔案大小（Groq 限制 25MB）
    file_size_mb = os.path.getsize(mp3_path) / (1024 * 1024)
    if file_size_mb > 25:
        raise HTTPException(
            status_code=400,
            detail=f"音訊檔案過大 ({file_size_mb:.1f}MB)，超過 Groq API 25MB 限制。",
        )

    data = {
        "model": model,
        "response_format": "verbose_json",
    }
    if language:
        data["language"] = language

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            with open(mp3_path, "rb") as f:
                files = {"file": ("audio.mp3", f, "audio/mpeg")}
                response = await client.post(
                    url, headers=headers, files=files, data=data
                )
    except httpx.RequestError as e:
        print(f"[ERROR] Groq request failed: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"連線至 Groq API 失敗: {str(e)}",
        )

    if response.status_code != 200:
        err_msg = response.text
        print(f"[ERROR] Groq API returned status {response.status_code}: {err_msg}")
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Groq Whisper API 轉譯失敗: {err_msg}",
        )

    try:
        verbose_data = response.json()
        return verbose_json_to_srt(verbose_data)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"解析 Groq 回應生成 SRT 失敗: {str(e)}",
        )


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------
class DownloadRequest(BaseModel):
    url: str


class TranscribeRequest(BaseModel):
    url: str
    language: Optional[str] = None
    model: Optional[str] = "whisper-large-v3"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/", summary="Health check")
async def root():
    has_groq_key = bool(os.getenv("GROQ_API_KEY", "").strip())
    return {
        "service": "YouTube MP3 & SRT API",
        "version": "1.1.0",
        "groq_api_key_configured": has_groq_key,
        "endpoints": {
            "MP3 下載": "GET/POST /download",
            "SRT 字幕生成": "GET/POST /transcribe",
        },
    }


# ----- MP3 下載端點 -----
@app.get("/download", summary="GET 下載 MP3 音訊")
async def download_mp3_get(
    background_tasks: BackgroundTasks,
    url: str = Query(..., description="YouTube 影片網址"),
):
    return await _process_download_mp3(url, background_tasks)


@app.post("/download", summary="POST 下載 MP3 音訊")
async def download_mp3_post(
    body: DownloadRequest,
    background_tasks: BackgroundTasks,
):
    return await _process_download_mp3(body.url, background_tasks)


async def _process_download_mp3(url: str, background_tasks: BackgroundTasks):
    if not url or not is_valid_youtube_url(url):
        raise HTTPException(status_code=400, detail="無效的 YouTube 網址。")

    job_dir = Path(tempfile.mkdtemp(dir=TEMP_DIR))

    try:
        filepath, filename, _ = download_as_mp3(url, job_dir)
    except yt_dlp.utils.DownloadError as e:
        cleanup_directory(str(job_dir))
        raise HTTPException(status_code=400, detail=f"下載失敗: {str(e)}")
    except Exception as e:
        cleanup_directory(str(job_dir))
        raise HTTPException(status_code=500, detail=f"處理失敗: {str(e)}")

    background_tasks.add_task(cleanup_directory, str(job_dir))

    encoded_filename = quote(filename)
    return FileResponse(
        path=filepath,
        filename=filename,
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
        },
    )


# ----- SRT 字幕生成端點 (Groq Whisper) -----
@app.get("/transcribe", summary="GET 提取 YouTube 語音並生成 SRT 字幕檔案")
async def transcribe_get(
    background_tasks: BackgroundTasks,
    url: str = Query(..., description="YouTube 影片網址"),
    language: Optional[str] = Query(
        None, description="語言代碼 (如 zh, en, ja)，不填則自動偵測"
    ),
    model: Optional[str] = Query(
        "whisper-large-v3", description="Groq Whisper 模型名稱"
    ),
):
    return await _process_transcribe(url, language, model, background_tasks)


@app.post("/transcribe", summary="POST 提取 YouTube 語音並生成 SRT 字幕檔案")
async def transcribe_post(
    body: TranscribeRequest,
    background_tasks: BackgroundTasks,
):
    return await _process_transcribe(
        body.url, body.language, body.model or "whisper-large-v3", background_tasks
    )


async def _process_transcribe(
    url: str,
    language: Optional[str],
    model: str,
    background_tasks: BackgroundTasks,
):
    if not url or not is_valid_youtube_url(url):
        raise HTTPException(status_code=400, detail="無效的 YouTube 網址。")

    video_id = extract_video_id(url)
    job_dir = Path(tempfile.mkdtemp(dir=TEMP_DIR))

    # 1. 快取檢查 (Cache Hit)：若該影片已轉譯過 SRT，直接使用快取回傳，節省時間與 API 額度
    if video_id:
        cached = get_cached_srt(video_id, language)
        if cached:
            title_base, srt_content = cached
            srt_filename = f"{title_base}.srt"
            srt_path = job_dir / srt_filename
            srt_path.write_text(srt_content, encoding="utf-8")

            background_tasks.add_task(cleanup_directory, str(job_dir))

            encoded_srt_filename = quote(srt_filename)
            return FileResponse(
                path=str(srt_path),
                filename=srt_filename,
                media_type="application/x-subrip",
                headers={
                    "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_srt_filename}",
                    "X-SRT-Cache": "HIT",
                },
            )

    # 2. 快取未命中 (Cache Miss)：檢查 API KEY
    if not os.getenv("GROQ_API_KEY", "").strip():
        cleanup_directory(str(job_dir))
        raise HTTPException(
            status_code=500,
            detail="伺服器未設定 GROQ_API_KEY，無法呼叫 Whisper 轉譯功能。請在 .env 檔案中設定 GROQ_API_KEY。",
        )

    try:
        # 下載 MP3 音訊
        mp3_path, _, title_base = download_as_mp3(url, job_dir)

        # 呼叫 Groq Whisper 轉成 SRT 字幕
        srt_content = await transcribe_with_groq(
            mp3_path, model=model, language=language
        )

        # 寫入 SRT 快取 (保留 SRT，MP3 將在背景被刪除)
        if video_id:
            save_srt_cache(video_id, language, title_base, srt_content)

        # 寫入本次請求的回傳 SRT 檔案
        srt_filename = f"{title_base}.srt"
        srt_path = job_dir / srt_filename
        srt_path.write_text(srt_content, encoding="utf-8")

    except yt_dlp.utils.DownloadError as e:
        cleanup_directory(str(job_dir))
        raise HTTPException(status_code=400, detail=f"影片下載失敗: {str(e)}")
    except HTTPException:
        cleanup_directory(str(job_dir))
        raise
    except Exception as e:
        cleanup_directory(str(job_dir))
        raise HTTPException(status_code=500, detail=f"轉譯處理失敗: {str(e)}")

    # 註冊背景清理任務（僅刪除本次請求的 MP3 音訊與暫存目錄，SRT 已存入快取）
    background_tasks.add_task(cleanup_directory, str(job_dir))

    # 回傳 SRT 檔案
    encoded_srt_filename = quote(srt_filename)
    return FileResponse(
        path=str(srt_path),
        filename=srt_filename,
        media_type="application/x-subrip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_srt_filename}",
            "X-SRT-Cache": "MISS",
        },
    )
