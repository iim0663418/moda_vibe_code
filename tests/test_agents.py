#!/usr/bin/env python3
"""
測試 VibeCodeMultiAgentSystem 初始化
"""

import asyncio
import logging
from config import get_settings
from autogen_agents import VibeCodeMultiAgentSystem

# 設定日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_agent_system():
    """測試 multi-agent system 初始化"""
    print("🧪 測試 VibeCodeMultiAgentSystem 初始化...")
    print("-" * 50)
    
    try:
        # 載入設定
        settings = get_settings()
        
        # 準備 MCP 配置
        mcp_config = {
            'fetch_url': settings.mcp_config.github_url,
            'brave_search_url': settings.mcp_config.brave_search_url,
            'github_url': settings.mcp_config.github_url,
            'timeout': settings.mcp_config.timeout
        }
        
        print("✅ 設定載入成功")
        print(f"   - Azure 端點: {settings.azure_openai_endpoint}")
        print(f"   - 部署名稱: {settings.azure_openai_deployment_name}")
        
        # 初始化 multi-agent system
        multi_agent_system = VibeCodeMultiAgentSystem(
            azure_openai_api_key=settings.azure_openai_api_key,
            azure_openai_endpoint=settings.azure_openai_endpoint,
            azure_openai_deployment_name=settings.azure_openai_deployment_name,
            mcp_config=mcp_config
        )
        
        print("✅ VibeCodeMultiAgentSystem 初始化成功")
        
        # 啟動系統
        print("🔄 正在啟動 multi-agent system...")
        await multi_agent_system.start()
        
        print("✅ Multi-agent system 啟動成功")
        
        # 測試簡單訊息
        print("🔄 正在測試簡單訊息...")
        result = await multi_agent_system.send_message("Hello, this is a test message")
        
        print("✅ 訊息發送測試成功")
        print(f"   - 最終回應: {result['final_response'][:100]}...")
        print(f"   - 對話訊息數: {result['total_messages']}")
        
        # 停止系統
        await multi_agent_system.stop()
        print("✅ Multi-agent system 已安全停止")
        
        print("\n🎉 所有測試通過！Azure OpenAI 與 AutoGen 整合運作正常。")
        return True
        
    except Exception as e:
        print(f"❌ 測試失敗: {e}")
        print(f"   錯誤類型: {type(e).__name__}")
        
        # 提供詳細的錯誤分析
        error_msg = str(e)
        if "404" in error_msg or "NotFound" in error_msg:
            print("\n💡 錯誤分析: 404 資源未找到")
            print("   可能原因:")
            print("   1. 部署名稱 (deployment name) 不正確")
            print("   2. Azure OpenAI 端點 URL 格式錯誤")
            print("   3. API 版本不支援")
        elif "401" in error_msg or "Unauthorized" in error_msg:
            print("\n💡 錯誤分析: 認證失敗")
            print("   可能原因:")
            print("   1. API Key 無效或過期")
            print("   2. API Key 權限不足")
        else:
            print(f"\n💡 錯誤分析: {error_msg}")
        
        return False

if __name__ == "__main__":
    asyncio.run(test_agent_system())
