#!/usr/bin/env python3
"""
Azure OpenAI API Key 偵錯工具
用於測試 .env 檔案中的 Azure OpenAI 配置是否正確
"""

import os
import asyncio
import logging
from dotenv import load_dotenv
from openai import AsyncAzureOpenAI

# 設定日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_env_config():
    """載入並驗證環境變數配置"""
    load_dotenv()
    
    config = {
        'api_key': os.getenv('AZURE_OPENAI_API_KEY'),
        'endpoint': os.getenv('AZURE_OPENAI_ENDPOINT'),
        'deployment_name': os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME'),
        'model': os.getenv('AZURE_OPENAI_MODEL'),
        'api_version': os.getenv('AZURE_OPENAI_API_VERSION', '2025-01-01-preview')
    }
    
    print("🔍 檢查環境變數配置...")
    print("-" * 50)
    
    issues = []
    
    for key, value in config.items():
        if not value:
            print(f"❌ {key}: 未設定")
            issues.append(f"{key} 未設定")
        elif key == 'api_key':
            # 遮蔽 API key 的部分內容
            masked_key = value[:8] + '*' * (len(value) - 16) + value[-8:] if len(value) > 16 else '*' * len(value)
            print(f"✅ {key}: {masked_key}")
        else:
            print(f"✅ {key}: {value}")
    
    if issues:
        print(f"\n❌ 發現 {len(issues)} 個配置問題:")
        for issue in issues:
            print(f"   - {issue}")
        return None, issues
    
    print("\n✅ 所有必要的環境變數都已設定")
    return config, []

async def test_azure_openai_connection(config):
    """測試 Azure OpenAI 連接"""
    print("\n🧪 測試 Azure OpenAI 連接...")
    print("-" * 50)
    
    try:
        # 創建客戶端
        client = AsyncAzureOpenAI(
            api_key=config['api_key'],
            api_version=config['api_version'],
            azure_endpoint=config['endpoint']
        )
        
        print("✅ Azure OpenAI 客戶端初始化成功")
        
        # 測試簡單的聊天完成
        print("🔄 正在測試聊天完成 API...")
        
        messages = [
            {"role": "user", "content": "請回覆 'API 測試成功'"}
        ]
        
        response = await client.chat.completions.create(
            model=config['deployment_name'],
            messages=messages,
            max_tokens=10,
            temperature=0.1
        )
        
        response_content = response.choices[0].message.content.strip()
        print(f"✅ API 回應: {response_content}")
        
        await client.close()
        
        print("\n🎉 Azure OpenAI API 測試完全成功！")
        return True, None
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Azure OpenAI API 測試失敗: {error_msg}")
        
        # 提供具體的錯誤分析
        if "401" in error_msg or "Unauthorized" in error_msg:
            print("\n💡 錯誤分析: API Key 認證失敗")
            print("   可能原因:")
            print("   1. API Key 錯誤或已過期")
            print("   2. API Key 沒有適當的權限")
            print("   3. 部署名稱 (AZURE_OPENAI_DEPLOYMENT_NAME) 不正確")
        elif "404" in error_msg or "NotFound" in error_msg:
            print("\n💡 錯誤分析: 資源未找到")
            print("   可能原因:")
            print("   1. Azure OpenAI 端點 URL 不正確")
            print("   2. 部署名稱不存在")
            print("   3. API 版本不支援")
        elif "429" in error_msg:
            print("\n💡 錯誤分析: 請求頻率限制")
            print("   請稍後再試")
        else:
            print("\n💡 錯誤分析: 其他連接問題")
            print("   請檢查網路連接和配置")
        
        return False, error_msg

def provide_setup_guidance():
    """提供設定指引"""
    print("\n📋 Azure OpenAI 設定指引")
    print("=" * 50)
    print("1. 確保您在 Azure 入口網站中有 Azure OpenAI 服務")
    print("2. 獲取您的 API Key 和端點 URL")
    print("3. 創建一個模型部署 (如 gpt-4.1-mini)")
    print("4. 在 .env 檔案中設定以下變數:")
    print()
    print("AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/")
    print("AZURE_OPENAI_DEPLOYMENT_NAME=your-deployment-name")
    print("AZURE_OPENAI_MODEL=gpt-4.1-mini-2025-04-14")
    print("AZURE_OPENAI_API_VERSION=2025-01-01-preview")
    print("AZURE_OPENAI_API_KEY=your-api-key")
    print()
    print("📚 更多資訊請參考: https://docs.microsoft.com/azure/cognitive-services/openai/")

async def main():
    """主要執行函數"""
    print("🚀 Azure OpenAI API Key 偵錯工具")
    print("=" * 50)
    
    # 載入配置
    config, issues = load_env_config()
    
    if issues:
        provide_setup_guidance()
        return
    
    # 測試連接
    success, error = await test_azure_openai_connection(config)
    
    if not success:
        print("\n🔧 修復建議:")
        print("-" * 30)
        print("1. 檢查 .env 檔案中的所有配置是否正確")
        print("2. 確認 API Key 是否有效且未過期")
        print("3. 驗證 Azure OpenAI 部署名稱是否正確")
        print("4. 檢查您的 Azure 訂閱是否有足夠的配額")
        
        provide_setup_guidance()
    else:
        print("\n✨ 所有配置都正常，您的應用程式應該能正常運作！")

if __name__ == "__main__":
    asyncio.run(main())
