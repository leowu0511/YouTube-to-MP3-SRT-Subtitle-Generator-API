# ---------- Stage: Build & Runtime ----------
FROM python:3.11-slim

# 系統環境設定
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 安裝 ffmpeg 與 deno (yt-dlp 預設 JS 執行環境)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl unzip nodejs git && \
    curl -fsSL https://deno.land/install.sh | sh && \
    cp /root/.deno/bin/deno /usr/local/bin/deno && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 建立工作目錄
WORKDIR /app

# 安裝 Python 依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製應用程式
COPY main.py .

# 建立暫存資料夾
RUN mkdir -p /tmp/yt_mp3_downloads

# 暴露埠號
EXPOSE 8000

# 啟動 Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
