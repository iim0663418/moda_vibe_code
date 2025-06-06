"""
測試 AutoGen Teams 功能
基於官方文檔範例的 Teams 系統測試
"""

import asyncio
import sys
import os

# 添加 app 目錄到 Python 路徑
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from autogen_teams_example import AutoGenTeamsManager
from config import get_settings

async def test_teams_functionality():
    """測試 Teams 功能"""
    print("=== AutoGen Teams 測試開始 ===")
    
    # 初始化設定
    settings = get_settings()
    print(f"Azure OpenAI 端點: {settings.azure_openai_endpoint}")
    print(f"部署名稱: {settings.azure_openai_deployment_name}")
    print(f"API 版本: {settings.azure_openai_api_version}")
    
    # 創建 Teams 管理器
    manager = AutoGenTeamsManager()
    
    try:
        # 初始化管理器
        print("\n--- 初始化 Teams 管理器 ---")
        await manager.initialize()
        print("✅ Teams 管理器初始化成功")
        
        # 測試反思團隊
        print("\n--- 測試反思團隊 (Reflection Team) ---")
        reflection_team = manager.create_reflection_team()
        print(f"✅ 反思團隊創建成功")
        
        # 執行詩歌創作任務（基於官方範例）
        poetry_task = "Write a short poem about the fall season."
        print(f"任務: {poetry_task}")
        
        result = await manager.run_team_task("reflection", poetry_task, stream=False)
        
        if result["success"]:
            print("✅ 反思團隊任務執行成功")
            print(f"任務 ID: {result.get('task_id', 'N/A')}")
            print(f"停止原因: {result['result']['stop_reason']}")
            print(f"訊息數量: {result['result']['message_count']}")
            print(f"執行時間: {result['metadata']['duration_seconds']:.2f} 秒")
            print(f"總 tokens: {result['metadata'].get('total_tokens', 0)}")
            
            print("\n--- 對話記錄 ---")
            for i, msg in enumerate(result['result']['messages'][:3]):  # 只顯示前3條訊息
                print(f"{i+1}. [{msg['source']}]: {msg['content'][:100]}...")
        else:
            print(f"❌ 反思團隊任務執行失敗: {result.get('error', '未知錯誤')}")
            print(f"錯誤類型: {result.get('error_type', 'unknown')}")
        
        # 測試研究團隊
        print("\n--- 測試研究團隊 (Research Team) ---")
        research_team = manager.create_research_team()
        print(f"✅ 研究團隊創建成功")
        
        # 執行簡短研究任務
        research_task = "Research the benefits of team collaboration in AI development."
        print(f"任務: {research_task}")
        
        research_result = await manager.run_team_task("research", research_task, stream=False, timeout=120)
        
        if research_result["success"]:
            print("✅ 研究團隊任務執行成功")
            print(f"任務 ID: {research_result.get('task_id', 'N/A')}")
            print(f"停止原因: {research_result['result']['stop_reason']}")
            print(f"訊息數量: {research_result['result']['message_count']}")
            print(f"執行時間: {research_result['metadata']['duration_seconds']:.2f} 秒")
        else:
            print(f"❌ 研究團隊任務執行失敗: {research_result.get('error', '未知錯誤')}")
            print(f"錯誤類型: {research_result.get('error_type', 'unknown')}")
        
        # 測試創意團隊
        print("\n--- 測試創意團隊 (Creative Team) ---")
        creative_team = manager.create_creative_team()
        print(f"✅ 創意團隊創建成功")
        
        # 執行創意寫作任務
        creative_task = "Write a brief product description for an AI-powered notebook."
        print(f"任務: {creative_task}")
        
        creative_result = await manager.run_team_task("creative", creative_task, stream=False)
        
        if creative_result["success"]:
            print("✅ 創意團隊任務執行成功")
            print(f"任務 ID: {creative_result.get('task_id', 'N/A')}")
            print(f"停止原因: {creative_result['result']['stop_reason']}")
            print(f"訊息數量: {creative_result['result']['message_count']}")
            print(f"執行時間: {creative_result['metadata']['duration_seconds']:.2f} 秒")
        else:
            print(f"❌ 創意團隊任務執行失敗: {creative_result.get('error', '未知錯誤')}")
            print(f"錯誤類型: {creative_result.get('error_type', 'unknown')}")
        
        # 測試重置功能
        print("\n--- 測試重置功能 ---")
        await manager.reset_team("reflection")
        print("✅ 反思團隊重置成功")
        
        print("\n=== 所有測試完成 ===")
        
    except Exception as e:
        print(f"❌ 測試過程中發生錯誤: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 關閉管理器
        await manager.close()
        print("✅ Teams 管理器已關閉")


async def test_error_handling():
    """測試錯誤處理"""
    print("\n=== 錯誤處理測試 ===")
    
    manager = AutoGenTeamsManager()
    
    try:
        await manager.initialize()
        manager.create_reflection_team()
        
        # 測試無效團隊名稱
        print("\n--- 測試無效團隊名稱 ---")
        try:
            result = await manager.run_team_task("invalid_team", "test task")
            print(f"❌ 預期錯誤但成功執行: {result}")
        except ValueError as e:
            print(f"✅ 正確捕獲 ValueError: {e}")
        
        # 測試空任務
        print("\n--- 測試空任務 ---")
        try:
            result = await manager.run_team_task("reflection", "")
            if not result["success"] and result.get("error_type") == "validation":
                print(f"✅ 正確處理空任務錯誤: {result['error']}")
            else:
                print(f"❌ 空任務處理不當: {result}")
        except ValueError as e:
            print(f"✅ 正確捕獲空任務錯誤: {e}")
        
        # 測試超長任務
        print("\n--- 測試超長任務 ---")
        long_task = "A" * 15000  # 超過 10000 字符限制
        try:
            result = await manager.run_team_task("reflection", long_task)
            if not result["success"] and result.get("error_type") == "validation":
                print(f"✅ 正確處理超長任務: {result['error']}")
            else:
                print(f"❌ 超長任務處理不當: {result}")
        except ValueError as e:
            print(f"✅ 正確捕獲超長任務錯誤: {e}")
        
        # 測試超時
        print("\n--- 測試超時功能 ---")
        result = await manager.run_team_task(
            "reflection", 
            "Write a very detailed analysis of quantum computing.", 
            timeout=1.0  # 1 秒超時
        )
        if not result["success"] and result.get("error_type") == "timeout":
            print(f"✅ 正確處理超時: {result['error']}")
        else:
            print(f"⚠️ 超時測試結果: {result.get('error', '未超時')}")
        
        print("\n--- 錯誤處理測試完成 ---")
        
    except Exception as e:
        print(f"❌ 錯誤處理測試失敗: {e}")
    
    finally:
        await manager.close()


async def test_concurrent_tasks():
    """測試並行任務"""
    print("\n=== 並行任務測試 ===")
    
    manager = AutoGenTeamsManager()
    
    try:
        await manager.initialize()
        
        # 創建不同團隊
        manager.create_reflection_team()
        manager.create_creative_team()
        
        # 並行執行任務
        tasks = [
            manager.run_team_task("reflection", "Write a haiku about spring.", timeout=60),
            manager.run_team_task("creative", "Create a slogan for a coffee shop.", timeout=60)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_count = 0
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"❌ 任務 {i+1} 發生異常: {result}")
            elif result.get("success"):
                print(f"✅ 任務 {i+1} 成功執行 (團隊: {result['team_name']})")
                success_count += 1
            else:
                print(f"❌ 任務 {i+1} 執行失敗: {result.get('error', '未知錯誤')}")
        
        print(f"並行任務完成: {success_count}/{len(tasks)} 成功")
        
    except Exception as e:
        print(f"❌ 並行任務測試失敗: {e}")
    
    finally:
        await manager.close()


async def test_api_compatibility():
    """測試 API 兼容性"""
    print("\n=== API 兼容性測試 ===")
    
    try:
        from teams_api import initialize_teams_manager, shutdown_teams_manager
        
        # 測試初始化函數
        await initialize_teams_manager()
        print("✅ API 初始化函數測試成功")
        
        # 測試關閉函數
        await shutdown_teams_manager()
        print("✅ API 關閉函數測試成功")
        
    except Exception as e:
        print(f"❌ API 兼容性測試失敗: {e}")


if __name__ == "__main__":
    print("AutoGen Teams 系統測試")
    print("基於官方文檔範例實現")
    print("=" * 50)
    
    # 運行測試
    asyncio.run(test_teams_functionality())
    asyncio.run(test_error_handling())
    asyncio.run(test_concurrent_tasks())
    asyncio.run(test_api_compatibility())
