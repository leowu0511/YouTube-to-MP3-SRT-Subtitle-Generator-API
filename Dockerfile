# ---------- Stage: Build & Runtime ----------
FROM python:3.11-slim

# 系統環境設定
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 安裝 ffmpeg（Debian slim 使用 apt）
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg nodejs && \
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
