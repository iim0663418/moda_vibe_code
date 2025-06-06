# Moda Vibe Code 多智能體系統優化實作計劃

## 概述
針對目前 "Send to Multi-Agent System 異常，但 Send to Azure OpenAI 正常" 的問題，實施多層次的優化與回退機制。

## 實作階段

### 階段 1: 多智能體系統回退機制 (優先實作)
- **目標**: 當 AutoGen 群組聊天失敗時，自動切換到單一 Azure OpenAI 呼叫模式
- **實作檔案**: `autogen_agents.py`
- **關鍵功能**:
  1. 設計多智能體模擬 prompt 模板
  2. 在 `send_message` 方法中加入回退邏輯
  3. 建立單一 Azure OpenAI 呼叫的多智能體協作模擬

### 階段 2: MCP Server 擴充機制
- **目標**: 抽象 MCP Server 管理，支持動態擴展與容錯
- **實作檔案**: `mcp_manager.py`
- **關鍵功能**:
  1. 定義 MCP Adapter 抽象類別
  2. 實作動態註冊與管理機制
  3. 加入容錯與重試策略

### 階段 3: 異常管理與用戶回饋
- **目標**: 提升系統韌性與用戶體驗
- **實作檔案**: `teams_api.py`, `frontend.html`, `logging_config.py`
- **關鍵功能**:
  1. 多層降級回應機制
  2. 前端智能體狀態面板
  3. 日誌強化與敏感資訊遮罩

### 階段 4: 協作流程自動化
- **目標**: 實現任務調度與狀態管理
- **實作檔案**: 新增 `workflow_engine.py`
- **關鍵功能**:
  1. 狀態機模型
  2. 任務派發與監控
  3. 配置化協作規則

## 當前實作重點

### 1. Azure OpenAI 單一呼叫多智能體模擬
建立 prompt 模板來模擬 fetcher、summarizer、analyzer、coordinator、responder 五個智能體的協作流程。

### 2. 回退機制設計
```python
async def send_message_with_fallback(self, content: str, recipient_agent_type: str = "coordinator"):
    try:
        # 嘗試使用原始多智能體系統
        return await self.send_message(content, recipient_agent_type)
    except (ResourceNotFoundError, GroupChatError) as e:
        # 使用 Azure OpenAI 單一呼叫回退方案
        return await self.fallback_single_agent_simulation(content)
```

### 3. 錯誤處理強化
- 針對不同錯誤類型實施不同的回退策略
- 記錄回退使用統計，便於系統優化

## 預期效果
1. 系統穩定性大幅提升，即使 AutoGen 群組聊天失敗也能正常運行
2. 用戶體驗改善，減少服務中斷時間
3. 便於後續擴展與優化

## 測試策略
1. 單元測試：各模組獨立功能測試
2. 整合測試：多智能體系統與回退機制協作測試
3. 壓力測試：異常場景下的系統穩定性測試
4. 用戶體驗測試：前端狀態顯示與錯誤回饋測試
