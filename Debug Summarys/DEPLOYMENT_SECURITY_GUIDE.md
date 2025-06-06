# Moda Vibe Code - 部署安全指南

## 📋 部署前檢查清單

### 1. 環境變數設定
- [ ] 複製 `.env.example` 到 `.env` 並填入正確的值
- [ ] 設定 Azure OpenAI API 金鑰和端點
- [ ] 設定 GitHub Personal Access Token
- [ ] 設定 Brave Search API 金鑰
- [ ] 設定 API_KEY（生產環境建議使用）
- [ ] 確認 ENVIRONMENT 設定為 `production`
- [ ] 設定適當的 LOG_LEVEL（生產環境建議使用 `INFO` 或 `WARNING`）

### 2. 安全性設定
- [ ] 啟用 API 金鑰驗證（設定 `API_KEY` 環境變數）
- [ ] 設定正確的 CORS 來源
- [ ] 確認 Rate Limiting 已啟用
- [ ] 檢查防火牆設定，僅允許必要端口

### 3. 容器安全
- [ ] 所有容器使用非 root 用戶運行
- [ ] 設定適當的資源限制（CPU、記憶體）
- [ ] 啟用健康檢查
- [ ] 使用最新的基礎映像

## 🔐 安全功能說明

### API 金鑰驗證
```bash
# 生成安全的 API 金鑰
openssl rand -base64 32
```

在 `.env` 檔案中設定：
```env
API_KEY=your-generated-api-key-here
```

### Rate Limiting
- 一般 API：每分鐘 100 次請求
- Chat API：每分鐘 20 次請求
- 基於 IP 地址和 User Agent 的組合識別

### 安全標頭
自動添加以下安全標頭：
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Strict-Transport-Security`
- `Content-Security-Policy`

### 輸入驗證與清理
- 聊天訊息：最大 5,000 字元
- 搜尋查詢：最大 500 字元
- SQL 查詢：最大 2,000 字元
- 移除有害字元（NULL bytes、控制字元）

## 🏗️ 部署步驟

### 1. 準備部署環境
```bash
# 克隆專案
git clone <repository-url>
cd moda_vibe_code

# 設定環境變數
cp .env.example .env
# 編輯 .env 檔案，填入正確的值
```

### 2. 建置與啟動
```bash
# 建置並啟動所有服務
docker-compose up --build -d

# 檢查服務狀態
docker-compose ps

# 查看日誌
docker-compose logs -f
```

### 3. 健康檢查
```bash
# 檢查主應用
curl http://localhost:8000/health

# 檢查 MCP 伺服器狀態
curl http://localhost:8000/mcp/status

# 檢查個別 MCP 伺服器
curl http://localhost:8000/mcp/github/status
curl http://localhost:8000/mcp/brave_search/status
curl http://localhost:8000/mcp/sqlite/status
```

## 🔍 MCP 伺服器監控

### 自動監控功能
- 每 30 秒自動健康檢查
- 失敗時自動重試
- 詳細的錯誤記錄
- 服務不可用時自動等待恢復

### 監控端點
- `GET /mcp/status` - 所有 MCP 伺服器狀態
- `GET /mcp/{server_id}/status` - 特定伺服器狀態
- `POST /mcp/{server_id}/health-check` - 強制健康檢查

### 故障排除
```bash
# 重啟特定 MCP 伺服器
docker-compose restart mcp-github
docker-compose restart mcp-brave-search
docker-compose restart mcp-sqlite

# 查看特定服務日誌
docker-compose logs mcp-github
docker-compose logs mcp-brave-search
docker-compose logs mcp-sqlite
```

## 📊 監控與日誌

### 日誌配置
- 結構化 JSON 日誌格式
- 自動日誌輪轉（10MB 每檔，保留 5 個檔案）
- 分離的錯誤日誌檔案
- 可配置的日誌層級

### 日誌位置
- 應用日誌：`app/logs/app.log`
- 錯誤日誌：`app/logs/error.log`
- Docker 日誌：`docker-compose logs`

### 監控指標
- 健康檢查狀態
- API 響應時間
- 錯誤率
- Rate Limiting 觸發次數

## 🚨 安全事件響應

### 常見安全事件
1. **Rate Limiting 觸發**
   - 檢查日誌中的客戶端 IP
   - 評估是否為惡意攻擊
   - 考慮調整 Rate Limit 設定

2. **API 金鑰洩漏**
   - 立即更換 API 金鑰
   - 檢查存取日誌
   - 通知相關人員

3. **MCP 伺服器異常**
   - 檢查伺服器健康狀態
   - 查看錯誤日誌
   - 必要時重啟服務

### 安全日誌審查
```bash
# 查看認證失敗的請求
docker-compose logs vibe-code-app | grep "401\|403"

# 查看 Rate Limiting 事件
docker-compose logs vibe-code-app | grep "429"

# 查看錯誤日誌
docker-compose logs vibe-code-app | grep "ERROR"
```

## 🔧 生產環境配置建議

### 環境變數
```env
# 生產環境設定
ENVIRONMENT=production
LOG_LEVEL=WARNING
API_KEY=<strong-api-key>
ENABLE_RATE_LIMITING=true

# CORS 設定（根據實際網域調整）
CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
```

### Docker Compose 生產配置
```yaml
# 添加到 docker-compose.yml
services:
  vibe-code-app:
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '1.0'
        reservations:
          memory: 1G
          cpus: '0.5'
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### 反向代理設定（Nginx 範例）
```nginx
server {
    listen 443 ssl http2;
    server_name yourdomain.com;
    
    ssl_certificate /path/to/certificate.crt;
    ssl_certificate_key /path/to/private.key;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Security headers
        add_header X-Frame-Options DENY;
        add_header X-Content-Type-Options nosniff;
        add_header X-XSS-Protection "1; mode=block";
    }
}
```

## 📈 效能優化

### 資源監控
```bash
# 監控容器資源使用
docker stats

# 監控磁碟使用
df -h
du -sh /var/lib/docker/

# 監控網路連線
netstat -tulpn | grep :8000
```

### 最佳化建議
1. **記憶體使用**
   - 監控 Python 應用的記憶體使用
   - 定期重啟容器以釋放記憶體

2. **磁碟空間**
   - 設定日誌輪轉
   - 定期清理 Docker 映像

3. **網路效能**
   - 使用 HTTP/2
   - 啟用 gzip 壓縮
   - 設定適當的快取標頭

## 🔄 備份與復原

### 資料備份
```bash
# 備份 SQLite 資料庫
docker-compose exec mcp-sqlite cp /data/mcp.db /data/backup/

# 備份應用日誌
docker cp vibe-code-app:/app/logs ./backup/logs-$(date +%Y%m%d)

# 備份環境設定
cp .env backup/.env-$(date +%Y%m%d)
```

### 災難復原
1. 保持 `.env` 檔案的安全備份
2. 記錄所有 API 金鑰和憑證
3. 準備快速部署腳本
4. 定期測試復原流程

## ⚠️ 已知限制與注意事項

1. **MCP 伺服器依賴**
   - GitHub MCP 需要有效的 Personal Access Token
   - Brave Search 需要有效的 API 金鑰
   - 網路連線問題可能影響服務可用性

2. **效能限制**
   - Rate Limiting 可能影響高頻使用
   - MCP 伺服器回應時間可能變化

3. **安全考量**
   - API 金鑰需定期更換
   - 監控異常存取模式
   - 保持依賴套件更新

## 📞 支援與聯絡

如遇到部署或安全問題，請：
1. 檢查應用日誌
2. 查看本指南的故障排除章節
3. 在專案 repository 建立 issue
4. 提供詳細的錯誤資訊和日誌
