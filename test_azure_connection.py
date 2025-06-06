"""
測試 Azure OpenAI 連接修正
"""

import asyncio
import logging
from autogen_teams_example import AutoGenTeamsManager
from config import get_settings

# 設置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_azure_connection():
    """測試 Azure OpenAI 連接是否正常"""
    print("正在測試 Azure OpenAI 連接修正...")
    
    try:
        # 初始化團隊管理器
        manager = AutoGenTeamsManager()
        
        # 嘗試初始化（這會執行連接測試）
        await manager.initialize()
        
        print("✅ Azure OpenAI 客戶端初始化成功！")
        print("✅ 連接測試通過，修正有效！")
        
        # 關閉連接
        await manager.close()
        
        return True
        
    except Exception as e:
        print(f"❌ 測試失敗: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(test_azure_connection())
