#!/usr/bin/env python3
"""
簡單的 Azure OpenAI 連線測試腳本
"""
import os
import sys
from dotenv import load_dotenv

def test_environment_variables():
    """檢查環境變數是否正確設定"""
    print("=== 檢查環境變數 ===")
    load_dotenv()
    
    required_vars = [
        'AZURE_OPENAI_ENDPOINT',
        'AZURE_OPENAI_API_KEY', 
        'AZURE_OPENAI_DEPLOYMENT_NAME'
    ]
    
    for var in required_vars:
        value = os.getenv(var)
        if not value:
            print(f"❌ {var}: 未設定")
            return False
        elif value in ['test-key', 'https://test.openai.azure.com']:
            print(f"❌ {var}: 仍為測試值")
            return False
        else:
            # 只顯示部分內容以保護敏感資訊
            if 'API_KEY' in var:
                display_value = f"{value[:8]}...{value[-4:]}" if len(value) > 12 else "***"
            else:
                display_value = value
            print(f"✅ {var}: {display_value}")
    
    return True

def test_openai_sdk():
    """使用 OpenAI SDK 測試連線"""
    print("\n=== 使用 OpenAI SDK 測試 ===")
    try:
        import openai
        load_dotenv()
        
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
        
        # 移除 extra_body 中的 Azure Search 部分，簡化測試
        client = openai.AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version="2024-10-21",  # 使用穩定版本
        )
        
        print(f"正在測試部署: {deployment}")
        completion = client.chat.completions.create(
            model=deployment,
            messages=[
                {
                    "role": "user",
                    "content": "請回答：1+1等於多少？",
                },
            ],
            max_tokens=50
        )
        
        response = completion.choices[0].message.content
        print(f"✅ OpenAI SDK 測試成功")
        print(f"回應: {response}")
        return True
        
    except Exception as e:
        print(f"❌ OpenAI SDK 測試失敗: {e}")
        return False

def test_autogen_azure_client():
    """測試 AutoGen 的 Azure 客戶端"""
    print("\n=== 測試 AutoGen Azure 客戶端 ===")
    try:
        load_dotenv()
        from autogen_ext.models.azure import AzureAIChatCompletionClient
        from azure.core.credentials import AzureKeyCredential
        
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
        
        # 清理 endpoint 格式
        clean_endpoint = endpoint.rstrip('/')
        
        client = AzureAIChatCompletionClient(
            model=deployment,
            endpoint=clean_endpoint,
            credential=AzureKeyCredential(api_key),
            model_info={
                "json_output": True,
                "function_calling": True,
                "vision": False,
                "family": "gpt",
                "structured_output": True,
            }
        )
        
        print(f"✅ AutoGen Azure 客戶端初始化成功")
        print(f"端點: {clean_endpoint}")
        print(f"部署: {deployment}")
        return True
        
    except Exception as e:
        print(f"❌ AutoGen Azure 客戶端初始化失敗: {e}")
        return False

def main():
    """主測試函數"""
    print("Azure OpenAI 連線診斷工具")
    print("=" * 50)
    
    # 測試環境變數
    if not test_environment_variables():
        print("\n❌ 環境變數設定有問題，請檢查 .env 檔案")
        return
    
    # 測試 OpenAI SDK
    openai_success = test_openai_sdk()
    
    # 測試 AutoGen 客戶端
    autogen_success = test_autogen_azure_client()
    
    print("\n" + "=" * 50)
    print("測試結果摘要:")
    print(f"OpenAI SDK: {'✅ 成功' if openai_success else '❌ 失敗'}")
    print(f"AutoGen 客戶端: {'✅ 成功' if autogen_success else '❌ 失敗'}")
    
    if openai_success and not autogen_success:
        print("\n🔍 建議: OpenAI SDK 可用但 AutoGen 客戶端失敗，可能是 AutoGen 配置問題")
    elif not openai_success:
        print("\n🔍 建議: 請檢查 Azure 入口網站中的端點、部署名稱和 API 金鑰設定")

if __name__ == "__main__":
    main()
