# YouTube to MP3 & SRT Subtitle Generator API

基於 **FastAPI + yt-dlp + ffmpeg + Groq Whisper API** 打造的 YouTube 音訊下載與 AI 語音轉字幕微服務。

輸入 YouTube 影片網址即可：
1. **下載 MP3 高音質音訊檔**
2. **呼叫 Groq Whisper API 自動生成帶時間軸的 SRT 字幕檔**（保留原始中文影片標題為檔名，無亂碼）

傳送完成後，服務會透過背景任務自動將伺服器上的所有暫存檔案徹底刪除。

---

## 系統特點

- **快速精準**：整合 Groq `whisper-large-v3` 模型，數秒內完成語音轉文字與時間軸對齊。
- **智能 SRT 快取機制**：伺服器會持久化快取 SRT 字幕，第二次請求同一影片時直接由快取秒級回傳，不重複消耗 Groq API 額度與下載頻寬。
- **MP3 音訊自動清理**：採用 FastAPI `BackgroundTasks`，MP3 音訊檔在傳輸或轉譯完成後會立即從伺服器刪除，不佔用硬碟空間。
- **檔名完整保留**：支援 UTF-8 (RFC 5987) 標準編碼，下載的 `.mp3` 與 `.srt` 檔案會完整保留原始中文標題。
- **Docker 化部署**：提供 Dockerfile 與 Docker Compose 配置（內建 Volume 掛載 `srt_cache`），適合一鍵部署至 VPS 伺服器。
- **防存取阻擋機制**：內建 yt-dlp 標頭與 Extractor 偽裝，有效防範 YouTube HTTP 403 阻擋。

---

## 專案結構

```text
.
├── main.py              # FastAPI 主程式（下載、轉譯、SRT 快取與背景清理邏輯）
├── requirements.txt     # Python 依賴套件
├── Dockerfile           # Docker 映像檔配置（含 ffmpeg 與 Python 3.11-slim）
├── docker-compose.yml   # Docker Compose 部署檔（含 Volume 持久化快取）
├── .env.example         # 環境變數設定範本
├── .gitignore           # Git 忽略檔案設定（防止 Key 意外外流）
└── README.md            # 本說明文件
```

---

## VPS 部署教學 (Docker Compose)

### 1. 複製專案到 VPS

```bash
git clone https://github.com/leowu0511/YouTube-to-MP3-SRT-Subtitle-Generator-API.git
cd YouTube-to-MP3-SRT-Subtitle-Generator-API
```

### 2. 設定 Groq API Key

複製範本並填入您的 Groq API Key（可在 [Groq Console](https://console.groq.com/keys) 申請）：

```bash
cp .env.example .env
nano .env
```

在 `.env` 中寫入 Key：
```env
GROQ_API_KEY=gsk_your_actual_groq_api_key_here
```

### 3. 啟動容器

```bash
docker compose up -d --build
```

### 4. 開放 VPS 防火牆（可選）

確保您的 VPS 防火牆（或雲端廠商 Security Group）已開放 **TCP 8000** 通訊埠：

```bash
sudo ufw allow 8000/tcp
sudo ufw reload
```

訪問 `http://<您的VPS_IP>:8000/` 或 `http://<您的VPS_IP>:8000/docs` 即可開啟互動式 API 文件。

---

## API 使用規格

### 1. 下載 MP3 音訊檔

- **Endpoint**: `POST /download` 或 `GET /download`
- **Content-Type**: `application/json`

#### POST 方式 (curl)
```bash
curl -L -X POST "http://<YOUR_SERVER_IP>:8000/download" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=phY1Vk1OOVc"}' \
  -o "music.mp3"
```

---

### 2. 生成 & 下載 SRT 字幕檔 (支援 SRT 快取)

- **Endpoint**: `POST /transcribe` 或 `GET /transcribe`
- **快取機制**:
  - **首次請求 (Cache Miss)**：下載音訊 ➔ 呼叫 Groq ➔ 儲存 SRT 快取 ➔ 自動刪除伺服器 MP3 音訊檔。
  - **第二次請求 (Cache Hit)**：直接由快取秒級回傳，不下載音訊、不呼叫 Groq API。

#### POST 方式 (curl)
```bash
curl -L -X POST "http://<YOUR_SERVER_IP>:8000/transcribe" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/watch?v=phY1Vk1OOVc",
    "language": "zh"
  }' \
  -o "subtitle.srt"
```

#### PowerShell 範例 (Windows)
```powershell
$body = @{
    url = "https://www.youtube.com/watch?v=phY1Vk1OOVc"
    language = "zh"
} | ConvertTo-Json

Invoke-WebRequest -Uri "http://<YOUR_SERVER_IP>:8000/transcribe" `
  -Method POST `
  -Body $body `
  -ContentType "application/json" `
  -OutFile "subtitle.srt"
```

---

## 維護與常用指令

```bash
# 查看容器即時日誌
docker compose logs -f

# 重新建置並重啟
docker compose up -d --build

# 停止服務
docker compose down
```

---

## 授權條款

MIT License
