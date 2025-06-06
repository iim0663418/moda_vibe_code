# Azure OpenAI API Key 偵錯修復總結

## 問題描述
原始錯誤：
```
openai.AuthenticationError: Error code: 401 - {'error': {'message': 'Incorrect API key provided: XmCvSPs7************************************************************************Mia9. You can find your API key at https://platform.openai.com/account/api-keys.',⁠ 'type': 'invalid_request_error', 'param': None, 'code': 'invalid_api_key'}}
```

## 根本原因分析
1. **API 客戶端配置錯誤**: `autogen_agents.py` 中的 `OpenAIChatCompletionClient` 沒有正確配置 Azure OpenAI API
2. **端點 URL 格式問題**: Azure OpenAI 需要特定的端點格式
3. **缺乏輸入驗證**: 沒有在應用程式啟動時驗證 API Key 的有效性

## 修復方案

### 1. 修復 Azure OpenAI 客戶端配置 ✅
**檔案**: `moda_vibe_code/app/autogen_agents.py`

**變更內容**:
- 加入 API Key 和端點的驗證邏輯
- 修正 `OpenAIChatCompletionClient` 的初始化參數
- 使用正確的 Azure OpenAI 端點格式
- 加入適當的錯誤處理和日誌記錄

**修復前**:
```python
self.model_client = OpenAIChatCompletionClient(
    model=azure_openai_model,
    api_key=azure_openai_api_key,
    api_base=azure_openai_endpoint,
    api_type="azure",
    api_version="2025-01-01-preview",
)
```

**修復後**:
```python
# 驗證 API Key 和端點
if not azure_openai_api_key or azure_openai_api_key == "test-key":
    raise ValueError("Azure OpenAI API key is required and cannot be empty or test value")

# 正確的 Azure OpenAI 配置
self.model_client = OpenAIChatCompletionClient(
    model=azure_openai_model,
    api_key=azure_openai_api_key,
    base_url=f"{azure_openai_endpoint}openai/deployments/{azure_openai_model}",
    api_version="2025-01-01-preview",
    extra_headers={"api-key": azure_openai_api_key}
)
```

### 2. 創建偵錯工具 ✅
**檔案**: `moda_vibe_code/debug_api_key.py`

**功能**:
- 檢查 `.env` 檔案中的所有必要配置
- 測試 Azure OpenAI API 連接
- 提供詳細的錯誤分析和修復建議
- 包含完整的設定指引

### 3. 環境變數配置檢查 ✅
**當前 `.env` 配置**:
```env
AZURE_OPENAI_ENDPOINT="https://iim20-m9w1b4wx-eastus2.cognitiveservices.azure.com/"
AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4.1-mini"
AZURE_OPENAI_MODEL="gpt-4.1-mini-2025-04-14"
AZURE_OPENAI_API_VERSION="2025-01-01-preview"
AZURE_OPENAI_API_KEY="XmCvSPs7eFdUzERPu5dPoEoYsuAYPC95gQcoktemvru9QjtGENKtJQQJ99BDACHYHv6XJ3w3AAAAACOGMia9"
```

## 偵錯工具使用方法

### 執行偵錯工具
```bash
cd moda_vibe_code
python debug_api_key.py
```

### 預期輸出
如果配置正確，您會看到：
```
🚀 Azure OpenAI API Key 偵錯工具
==================================================
🔍 檢查環境變數配置...
--------------------------------------------------
✅ api_key: XmCvSPs7********ACOGMia9
✅ endpoint: https://iim20-m9w1b4wx-eastus2.cognitiveservices.azure.com/
✅ deployment_name: gpt-4.1-mini
✅ model: gpt-4.1-mini-2025-04-14
✅ api_version: 2025-01-01-preview

✅ 所有必要的環境變數都已設定

🧪 測試 Azure OpenAI 連接...
--------------------------------------------------
✅ Azure OpenAI 客戶端初始化成功
🔄 正在測試聊天完成 API...
✅ API 回應: API 測試成功

🎉 Azure OpenAI API 測試完全成功！

✨ 所有配置都正常，您的應用程式應該能正常運作！
```

## 常見錯誤及解決方案

### 1. 401 Unauthorized 錯誤
**原因**: API Key 無效或過期
**解決方案**:
- 檢查 Azure 入口網站中的 API Key
- 確認 API Key 沒有過期
- 驗證部署名稱是否正確

### 2. 404 Not Found 錯誤
**原因**: 端點 URL 或部署名稱錯誤
**解決方案**:
- 確認 Azure OpenAI 端點 URL 格式正確
- 檢查部署名稱是否存在於您的 Azure OpenAI 資源中

### 3. 429 Rate Limiting 錯誤
**原因**: 請求頻率過高
**解決方案**:
- 等待一段時間後重試
- 檢查您的配額設定

## 預防措施

### 1. 啟動時驗證
在應用程式啟動時執行配置驗證：
```python
# 在 main.py 的 lifespan 函數中加入
try:
    # 驗證 Azure OpenAI 配置
    if not settings.azure_openai_api_key or settings.azure_openai_api_key == "test-key":
        logger.error("Azure OpenAI API key not properly configured")
        # 可以選擇是否要阻止應用程式啟動
except Exception as e:
    logger.error(f"Configuration validation failed: {e}")
```

### 2. 健康檢查端點
現有的 `/health` 端點可以擴展以包含 Azure OpenAI 連接檢查：
```python
@app.get("/health/azure-openai")
async def azure_openai_health():
    """檢查 Azure OpenAI 服務健康狀態"""
    try:
        # 執行簡單的 API 測試
        return {"status": "healthy", "service": "azure-openai"}
    except Exception as e:
        return {"status": "unhealthy", "service": "azure-openai", "error": str(e)}
```

## 測試驗證

### 執行偵錯工具
```bash
python debug_api_key.py
```

### 重啟應用程式
```bash
cd moda_vibe_code/app
python main.py
```

### 測試 API 端點
```bash
curl -X POST "http://localhost:8000/azure-openai" \
     -H "Content-Type: application/json" \
     -d '{"prompt": "Hello, this is a test"}'
```

## 維護建議

1. **定期檢查 API Key**: 設定提醒以在 API Key 過期前更新
2. **監控使用量**: 定期檢查 Azure OpenAI 的使用量和配額
3. **備份配置**: 確保 `.env` 檔案在版本控制之外，但有安全的備份
4. **日誌監控**: 監控應用程式日誌以及早發現 API 相關問題

## 相關文件
- [Azure OpenAI 官方文件](https://docs.microsoft.com/azure/cognitive-services/openai/)
- [AutoGen 文件](https://microsoft.github.io/autogen/)
- [OpenAI Python SDK](https://platform.openai.com/docs/libraries/python-library)
