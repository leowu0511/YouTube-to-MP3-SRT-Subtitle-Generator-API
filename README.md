# YouTube to MP3 & SRT Subtitle Generator API

基於 **FastAPI + yt-dlp + ffmpeg + Groq Whisper API** 打造的 YouTube 音訊下載與 AI 語音轉字幕微服務。

輸入 YouTube 影片網址即可：
1. **下載 MP3 高音質音訊檔**
2. **呼叫 Groq Whisper API 自動生成帶時間軸的 SRT 字幕檔**（保留原始中文影片標題為檔名，無亂碼）

傳送完成後，服務會透過背景任務自動將伺服器上的所有暫存檔案徹底刪除。

---

## 🛠️ 本專案具體實現與技術細節

### 1. 🎵 高音質 MP3 音訊轉換 (`/download`)
- 整合 `yt-dlp` 與 `ffmpeg` 自動提取最佳音訊流並轉換為 192kbps MP3 檔案。
- 採用串流傳輸，下載完成後自動觸發背景任務釋放硬碟空間。

### 2. 📝 Groq Whisper AI 語音轉字幕 (`/transcribe`)
- 自動將音訊傳送至 Groq `whisper-large-v3` 模型進行語音辨識與時間軸對齊。
- 將 Whisper 的回應自動轉換為標準 SRT 字幕格式（含 `HH:MM:SS,mmm` 時間軸與序號）。

### 3. 💾 智能 SRT 快取機制 (Sub-second SRT Cache)
- 提取 YouTube 11 位元影片 ID 作為索引，將生成好的 SRT 字幕與原標題永久保存至 `srt_cache/` 資料夾（已配置 Docker Volume 持久化儲存）。
- **Cache Hit 秒級回傳**：二次請求同一影片時直接由快取回傳，**反應時間僅約 0.3 秒**，不重複消耗 Groq API 額度與流量。

### 4. 🧹 伺服器硬碟零殘留自動清理 (Zero-Footprint Cleanup)
- 採用 FastAPI `BackgroundTasks` 異步任務機制。
- MP3 音訊檔在使用者下載完畢或轉譯完成後，會**立即徹底刪除**，避免 VPS 硬碟爆滿。

### 5. 🔤 檔名 UTF-8 標準編碼 (RFC 5987)
- 提取原始影片標題（包含繁體中文、Unicode 與特殊字元）並進行檔名安全過濾。
- 採用 HTTP 標頭 `Content-Disposition: attachment; filename*=UTF-8''...` 標準，確保瀏覽器與各式命令列工具下載後**檔名完全不亂碼**。

### 6. 🛡️ VPS 機房 IP 防封鎖與 JavaScript 挑戰解答器
- **Deno JS 執行環境**：在 Docker 映像檔中內建 `deno` 與 `ejs:github` 組件，自動解開 YouTube JS 挑戰與 n-sig 加密。
- **Cookies 自動載入與唯讀保護處理**：自動掃描並載入專案目錄下的 `*cookies*.txt`（如 `www.youtube.com_cookies.txt`），並在運行時自動複製至可寫入暫存區，解決 Linux Read-only 限制並徹底解除 YouTube `Sign in to confirm you're not a bot` 阻擋。

### 7. 🐳 Docker & Docker Compose 輕量化部署
- 基於 `python:3.11-slim` 打造輕量 Docker 映像檔，內建 `ffmpeg`、`nodejs` 與 `deno`。
- 配置 Docker Compose，提供埠號對應、自動重啟與快取目錄掛載。

---

## 📁 專案結構

```text
.
├── main.py              # FastAPI 主程式（下載、轉譯、SRT 快取與背景清理邏輯）
├── requirements.txt     # Python 依賴套件
├── Dockerfile           # Docker 映像檔配置（含 ffmpeg, deno 與 Python 3.11-slim）
├── docker-compose.yml   # Docker Compose 部署檔（含 Volume 持久化快取）
├── .env.example         # 環境變數設定範本
├── .gitignore           # Git 忽略檔案設定（防止 Key 與 Cookies 意外外流）
└── README.md            # 本說明文件
```

---

## 🚀 VPS 部署教學 (Docker Compose)

### 1. 複製專案到 VPS

```bash
git clone https://github.com/leowu0511/YouTube-to-MP3-SRT-Subtitle-Generator-API.git
cd YouTube-to-MP3-SRT-Subtitle-Generator-API
```

### 2. 設定 Groq API Key

複製範本並填入您的 Groq API Key（可在 [Groq Console](https://console.groq.com/keys) 免費申請）：

```bash
cp .env.example .env
nano .env
```

在 `.env` 中寫入 Key：
```env
GROQ_API_KEY=gsk_your_actual_groq_api_key_here
```

### 3. (選填) 放置 YouTube Cookies
若您的 VPS 機房 IP 遭到 YouTube 強制驗證，請將從瀏覽器匯出的 `cookies.txt` 或 `www.youtube.com_cookies.txt` 放入本專案目錄下即可。

### 4. 一鍵啟動容器

```bash
docker compose up -d --build
```

### 5. 開放 VPS 防火牆（可選）

確保您的 VPS 防火牆（或雲端廠商 Security Group）已開放 **TCP 8000** 通訊埠：

```bash
sudo ufw allow 8000/tcp
sudo ufw reload
```

訪問 `http://<您的VPS_IP>:8000/` 或 `http://<您的VPS_IP>:8000/docs` 即可開啟互動式 API 文件。

---

## 📡 API 使用規格

### 1. 下載 MP3 音訊檔 (傳輸後自動刪除伺服器 MP3)

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
  - **第二次請求 (Cache Hit)**：直接由快取秒級回傳 (約 0.3 秒)，不下載音訊、不呼叫 Groq API。

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

## 🛠️ 維護與常用指令

```bash
# 查看容器即時日誌
docker compose logs -f

# 重新建置並重啟
docker compose up -d --build

# 停止服務
docker compose down
```

---

## 📄 授權條款

MIT License
