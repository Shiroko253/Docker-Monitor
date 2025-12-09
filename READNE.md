# Docker 容器監控系統

一個基於 Discord Webhook 的 Docker 容器即時監控工具,能智能判斷容器的崩潰、重啟和正常停止狀態。

## ✨ 功能特點

- 🔍 **即時事件監聽** - 監控容器的啟動、停止、重啟等所有狀態變化
- 🧠 **智能狀態判斷** - 準確區分容器是崩潰、正常停止還是自動重啟
- 📊 **網絡流量監控** - 定期檢測容器的網絡使用情況
- 💬 **Discord 通知** - 所有事件即時推送到 Discord 頻道
- 📋 **動態狀態面板** - 自動更新的容器狀態總覽(編輯同一條消息)

## 📦 系統架構

```
project/
├── docker-compose.yml       # Docker Compose 配置
├── monitor.py              # 監控程序主文件
├── app1/                   # 你的第一個應用
│   ├── Dockerfile
│   └── .env
├── app2/                   # 你的第二個應用
│   ├── Dockerfile
│   └── .env
└── app3/                   # 你的第三個應用
    ├── Dockerfile
    └── .env
```

## 🚀 快速開始

### 1. 獲取 Discord Webhook URL

1. 進入你的 Discord 伺服器
2. 選擇一個頻道 → 右鍵 → **編輯頻道**
3. 左側選單選擇 **整合** → **Webhook**
4. 點擊 **新 Webhook** → 複製 **Webhook URL**

### 2. 配置監控程序

編輯 `monitor.py`,修改以下配置:

```python
# ===== 配置區 =====
WEBHOOK_URL = "你的_Discord_Webhook_URL"
MONITORED_CONTAINERS = ["app1", "app2", "app3"]  # 要監控的容器名稱
NETWORK_CHECK_INTERVAL = 60      # 網絡檢查間隔(秒)
NETWORK_THRESHOLD = 10 * 1024 * 1024  # 流量閾值 10MB
```

### 3. 配置 Docker Compose

創建 `docker-compose.yml`:

```yaml
version: '3.8'

services:
  # === 你的應用容器 ===
  app1:
    build: ./app1
    container_name: app1
    restart: always
    env_file:
      - ./app1/.env
    networks:
      - monitoring

  app2:
    build: ./app2
    container_name: app2
    restart: always
    env_file:
      - ./app2/.env
    networks:
      - monitoring

  app3:
    build: ./app3
    container_name: app3
    restart: always
    env_file:
      - ./app3/.env
    networks:
      - monitoring

  # === Docker 監控器 ===
  docker-monitor:
    image: python:3.9-slim
    container_name: docker-monitor
    restart: unless-stopped
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./monitor.py:/app/monitor.py:ro
    working_dir: /app
    command: >
      sh -c "pip install docker requests && python monitor.py"
    networks:
      - monitoring
    depends_on:
      - app1
      - app2
      - app3

networks:
  monitoring:
    driver: bridge
```

### 4. 啟動服務

```bash
# 啟動所有容器(包括監控器)
docker compose up -d

# 查看監控器日誌
docker logs -f docker-monitor

# 停止所有服務(保留容器)
docker compose stop

# 停止並刪除所有容器
docker compose down
```

## 📊 監控功能說明

### 狀態判斷邏輯

監控器會根據以下信息智能判斷容器狀態:

| 狀態 | 判斷條件 | 通知顏色 |
|------|---------|---------|
| 💥 **崩潰** | 退出碼 > 0 | 🔴 紅色 |
| 🛑 **正常停止** | 退出碼 = 0 | 🟠 橙色 |
| 🔄 **重啟中** | 有重啟策略且在重啟窗口內 | 🟡 黃色 |
| 🟢 **已啟動** | 容器成功啟動 | 🟢 綠色 |

### Discord 通知類型

1. **系統啟動通知** - 監控器啟動時發送
2. **狀態變更通知** - 容器狀態改變時發送,包含退出碼和重啟策略
3. **網絡流量通知** - 檢測到大量流量時發送
4. **動態狀態面板** - 持續更新的容器總覽(編輯同一條消息)

## ⚙️ 進階配置

### 調整網絡監控靈敏度

```python
NETWORK_CHECK_INTERVAL = 30   # 更頻繁檢查(30秒)
NETWORK_THRESHOLD = 5 * 1024 * 1024  # 更低的閾值(5MB)
```

### 調整重啟檢測窗口

```python
RESTART_DETECTION_WINDOW = 10  # 延長到 10 秒
```

### 修改日誌級別

```python
logging.basicConfig(
    level=logging.DEBUG,  # 改為 DEBUG 查看更多信息
    format='%(asctime)s - %(levelname)s - %(message)s'
)
```

## 🔧 故障排除

### 監控器無法連接到 Docker

**錯誤**: `Error while fetching server API version`

**解決方案**:
```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock:ro  # 確保掛載正確
```

### Discord 通知沒有發送

**檢查清單**:
1. ✅ Webhook URL 格式正確 (以 `https://discord.com/api/webhooks/` 開頭)
2. ✅ 容器名稱與 `MONITORED_CONTAINERS` 匹配
3. ✅ 監控器容器有網絡連接
4. ✅ 查看監控器日誌: `docker logs docker-monitor`

### 狀態面板沒有更新

Discord Webhook 編輯消息有速率限制,如果更新過於頻繁可能會失敗。這是正常現象,不影響通知功能。

## 📝 注意事項

1. **Docker Socket 權限** - 監控器需要訪問 `/var/run/docker.sock`,只給予只讀權限 (`:ro`)
2. **容器命名** - `MONITORED_CONTAINERS` 中的名稱必須與 `container_name` 完全一致
3. **重啟策略** - 監控器會讀取容器的重啟策略來判斷行為
4. **網絡限制** - 監控器必須能訪問 `discord.com` 域名

## 📜 授權

本項目採用 [MIT License](LICENSE) 授權。

```
MIT License

Copyright (c) 2024

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

**提示**: 首次運行時,建議先查看監控器日誌確保正常運行:
```bash
docker logs -f docker-monitor
```
