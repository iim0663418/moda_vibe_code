# moda_vibe_code

`moda_vibe_code` 是一個基於 FastAPI 的多代理系統，整合了 Azure OpenAI 和 Model Context Protocol (MCP)，並具備工作流程狀態機、團隊協作和安全功能。

## 主要功能

*   **多代理系統**：利用 AutoGen 框架實現智能代理之間的協作。
*   **Azure OpenAI 整合**：支援透過 Azure OpenAI 服務進行語言模型互動。
*   **Model Context Protocol (MCP) 整合**：與 MCP 伺服器（如 GitHub、Brave Search、SQLite）進行互動，擴展代理能力。
*   **工作流程狀態機**：基於 `transitions` 庫實現任務的生命週期管理，支援任務創建、啟動、取消、重試和狀態追蹤。
*   **團隊協作**：提供團隊管理和代理協作功能。
*   **安全功能**：包含 API 金鑰驗證、速率限制、輸入清理和安全標頭。
*   **日誌和監控**：提供詳細的日誌記錄和系統健康檢查端點。

## 技術棧

*   **後端框架**：FastAPI
*   **多代理框架**：AutoGen
*   **AI 服務**：Azure OpenAI
*   **任務佇列**：Celery (搭配 Redis)
*   **狀態機**：Transitions
*   **環境管理**：python-dotenv
*   **HTTP 客戶端**：httpx
*   **配置管理**：PyYAML
*   **監控**：prometheus-client
*   **容器化**：Docker, Docker Compose

## 安裝與設定

1.  **複製專案**：
    ```bash
    git clone https://github.com/your-repo/moda_vibe_code.git
    cd moda_vibe_code
    ```
2.  **建立虛擬環境並安裝依賴**：
    ```bash
    python -m venv venv
    source venv/bin/activate  # Windows: venv\Scripts\activate
    pip install -r requirements.txt
    ```
3.  **設定環境變數**：
    複製 `.env.example` 為 `.env` 並填寫必要的 Azure OpenAI API 金鑰和端點資訊，以及其他服務（如 Redis、MCP 伺服器）的 URL。
    ```env
    # Azure OpenAI
    AZURE_OPENAI_API_KEY="your_azure_openai_api_key"
    AZURE_OPENAI_ENDPOINT="your_azure_openai_endpoint"
    AZURE_OPENAI_DEPLOYMENT_NAME="your_deployment_name"
    AZURE_OPENAI_API_VERSION="2023-05-15" # 或您使用的 API 版本

    # Application Settings
    APP_NAME="Moda Vibe Code"
    APP_VERSION="0.1.0"
    ENVIRONMENT="development" # development, staging, or production
    HOST="0.0.0.0"
    PORT=8000
    RELOAD=true
    LOG_LEVEL="INFO" # DEBUG, INFO, WARNING, ERROR, CRITICAL
    CORS_ORIGINS="*" # 或指定允許的來源，例如 "http://localhost:3000,http://127.0.0.1:3000"

    # Security
    API_KEY_SECRET="your_strong_api_key_secret" # 用於 API 金鑰驗證

    # MCP Configuration
    MCP_GITHUB_URL="http://localhost:7001" # 範例 URL，請替換為實際的 MCP GitHub 伺服器 URL
    MCP_BRAVE_SEARCH_URL="http://localhost:7002" # 範例 URL，請替換為實際的 MCP Brave Search 伺服器 URL
    MCP_SQLITE_URL="http://localhost:7003" # 範例 URL，請替換為實際的 MCP SQLite 伺服器 URL
    MCP_TIMEOUT=30 # MCP 請求超時時間 (秒)

    # Celery and Redis
    CELERY_BROKER_URL="redis://localhost:6379/0"
    CELERY_RESULT_BACKEND="redis://localhost:6379/0"

    # Teams API (如果使用)
    TEAMS_WEBHOOK_URL="your_teams_webhook_url" # Microsoft Teams Webhook URL
    ```
4.  **啟動應用程式**：
    ```bash
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
    ```
    或使用 Docker Compose 啟動 (請確保 `docker-compose.yml` 已正確配置，特別是環境變數和卷掛載)：
    ```bash
    docker-compose up --build
    ```

## API 端點 (部分主要端點)

*   `GET /`: 服務前端 HTML 介面。
*   `GET /health`: 應用程式健康檢查。
*   `POST /azure-openai`: 直接與 Azure OpenAI 進行聊天補全。
    *   請求主體: `{"prompt": "你的提示詞"}`
*   `POST /chat` (需 API 金鑰): 與多代理系統進行聊天。
    *   請求主體: `{"message": "你的訊息", "agent_type": "coordinator"}`
*   `POST /multi-agent/send`: 向多代理系統發送消息。
    *   請求主體: `{"content": "你的內容", "recipient_agent_type": "researcher"}`
*   `GET /multi-agent/status`: 獲取多代理系統狀態。
*   `POST /workflow/create`: 創建新的工作流程任務。
    *   請求主體: `{"task_id": "unique_task_id", "workflow_name": "default_workflow", "user_input": "任務描述", "priority": "normal"}`
*   `POST /workflow/{task_id}/start`: 啟動工作流程任務。
*   `GET /workflow/{task_id}/status`: 獲取工作流程任務詳細狀態。
*   `GET /mcp/status`: 獲取所有 MCP 伺服器狀態。
*   `GET /mcp-github/repos` (需 API 金鑰): 透過 MCP 伺服器列出 GitHub 儲存庫。
*   `GET /mcp-brave-search/search` (需 API 金鑰): 透過 MCP 伺服器執行 Brave 搜尋。
    *   查詢參數: `?query=你的搜尋關鍵字`

## 專案結構

```
.
├── main.py                 # FastAPI 應用程式主入口
├── app/                    # 應用程式相關檔案
│   └── frontend.html       # 簡單的前端使用者介面
├── autogen_agents.py       # AutoGen 多代理系統的實現
├── workflow_state_machine.py # 工作流程狀態機的實現
├── teams_api.py            # 團隊協作相關 API
├── config.py               # 應用程式配置設定 (Pydantic models)
├── logging_config.py       # 日誌配置
├── security.py             # 安全相關功能 (API 金鑰、速率限制等)
├── mcp_manager.py          # MCP 伺服器管理和請求處理
├── models.py               # Pydantic 數據模型 (請求/回應模型)
├── agent_tasks.py          # Celery 任務定義 (如果適用)
├── app/requirements.txt    # Python 依賴
├── .env.example            # 環境變數範本
├── .env                    # 環境變數檔案 (請勿提交到版本控制)
├── Dockerfile              # 主要應用程式的 Dockerfile
├── docker-compose.yml      # Docker Compose 配置，用於啟動應用程式及其依賴服務
├── LICENSE                 # 專案授權檔案
├── config/                 # 配置檔案目錄
│   └── agent_collaboration_rules.yaml # 代理協作規則範例
├── tests/                  # 測試腳本目錄
│   ├── test_agents.py
│   ├── test_azure_connection.py
│   ├── test_azure_simple.py
│   ├── test_fallback_mechanism.py
│   ├── test_multi_agent_automation.py
│   └── test_teams.py
├── scripts/                # 各類輔助腳本
│   ├── debug_api_key.py
│   └── fix_ssl_issue.py
├── docs/                   # 文件和說明文檔
│   └── Debug Summarys/     # 開發過程中的調試摘要和筆記 (可考慮進一步整理)
├── mcp-github/             # MCP GitHub 伺服器相關檔案 (如果在本專案中管理)
│   └── Dockerfile          # MCP GitHub 伺服器的 Dockerfile
└── mcp-brave-search/       # MCP Brave Search 伺服器相關檔案 (如果在本專案中管理)
    └── Dockerfile          # MCP Brave Search 伺服器的 Dockerfile
```

## 貢獻

歡迎各種形式的貢獻！如果您想為此專案做出貢獻，請遵循以下步驟：

1.  Fork 此儲存庫。
2.  為您的功能或錯誤修復創建一個新的分支 (`git checkout -b feature/your-feature-name`)。
3.  提交您的更改 (`git commit -am 'Add some feature'`)。
4.  將您的分支推送到遠程儲存庫 (`git push origin feature/your-feature-name`)。
5.  創建一個新的 Pull Request。

請確保您的程式碼遵循專案的編碼風格，並包含適當的測試。

## 授權

本專案採用 [LICENSE](LICENSE) 中定義的授權 (如果 `LICENSE` 檔案存在)。如果沒有 `LICENSE` 檔案，則預設為專有軟體。
