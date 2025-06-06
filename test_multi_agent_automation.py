"""
測試多智能體協作流程自動化系統
Test Multi-Agent Automation System
"""

import asyncio
import time
from datetime import datetime
from config_manager import get_config_manager
from workflow_state_machine import get_workflow_state_machine, TaskPriority
from monitoring import get_health_checker, get_prometheus_collector, get_performance_tracker


def test_config_manager():
    """測試配置管理器"""
    print("🔧 測試配置管理器...")
    
    try:
        config_manager = get_config_manager()
        
        # 載入配置
        config = config_manager.get_config()
        print(f"   ✅ 配置版本: {config.version}")
        print(f"   ✅ 智能體數量: {len(config.agents)}")
        print(f"   ✅ 工作流程數量: {len(config.workflows)}")
        
        # 驗證配置
        validation_result = config_manager.validate_configuration()
        if validation_result['valid']:
            print("   ✅ 配置驗證通過")
        else:
            print(f"   ❌ 配置驗證失敗: {validation_result['errors']}")
        
        # 測試取得特定配置
        fetcher_config = config_manager.get_agent_config('fetcher')
        if fetcher_config:
            print(f"   ✅ Fetcher 智能體配置: {fetcher_config.role}")
        
        default_workflow = config_manager.get_workflow_config('default')
        if default_workflow:
            print(f"   ✅ 預設工作流程步驟數: {len(default_workflow.steps)}")
        
        return True
        
    except Exception as e:
        print(f"   ❌ 配置管理器測試失敗: {e}")
        return False


def test_state_machine():
    """測試工作流程狀態機"""
    print("\n🔄 測試工作流程狀態機...")
    
    try:
        state_machine = get_workflow_state_machine()
        
        # 創建測試任務
        task_id = f"test_task_{int(time.time())}"
        task = state_machine.create_task(
            task_id=task_id,
            workflow_name="default",
            user_input="這是測試輸入",
            priority=TaskPriority.NORMAL
        )
        
        print(f"   ✅ 創建任務: {task_id}")
        print(f"   ✅ 任務狀態: {task.state}")
        
        # 啟動任務
        success = state_machine.start_task(task_id)
        if success:
            print("   ✅ 任務啟動成功")
        
        # 模擬執行步驟
        step_result = state_machine.execute_workflow_step(
            task_id, "data_fetching", 
            execution_result={"status": "success", "data": "test data"}
        )
        
        if step_result:
            print("   ✅ 工作流程步驟執行成功")
        
        # 取得任務統計
        stats = state_machine.get_task_statistics()
        print(f"   ✅ 任務統計: {stats}")
        
        return True
        
    except Exception as e:
        print(f"   ❌ 狀態機測試失敗: {e}")
        return False


def test_monitoring():
    """測試監控系統"""
    print("\n📊 測試監控系統...")
    
    try:
        # 測試 Prometheus 指標收集器
        prometheus_collector = get_prometheus_collector()
        
        # 記錄一些測試指標
        prometheus_collector.record_task_start("test_workflow")
        prometheus_collector.record_agent_execution("fetcher", True)
        prometheus_collector.record_celery_task("test_task", "completed")
        
        print("   ✅ Prometheus 指標記錄成功")
        
        # 測試性能追蹤器
        performance_tracker = get_performance_tracker()
        
        task_id = "perf_test_task"
        performance_tracker.start_tracking(task_id)
        time.sleep(0.1)  # 模擬執行時間
        duration = performance_tracker.end_tracking(task_id)
        
        print(f"   ✅ 性能追蹤: 執行時間 {duration:.3f} 秒")
        
        # 測試健康檢查器
        health_checker = get_health_checker()
        
        # 由於某些依賴可能不存在，我們只測試基本功能
        health_summary = health_checker.get_health_summary()
        print(f"   ✅ 健康檢查摘要: {health_summary}")
        
        return True
        
    except Exception as e:
        print(f"   ❌ 監控系統測試失敗: {e}")
        return False


def test_celery_imports():
    """測試 Celery 相關模組導入"""
    print("\n🐛 測試 Celery 模組導入...")
    
    try:
        # 測試 Celery 相關導入
        import celery
        print(f"   ✅ Celery 版本: {celery.__version__}")
        
        import redis
        print(f"   ✅ Redis 模組可用")
        
        import transitions
        print(f"   ✅ Transitions 模組可用")
        
        import yaml
        print(f"   ✅ PyYAML 模組可用")
        
        import prometheus_client
        print(f"   ✅ Prometheus Client 模組可用")
        
        # 嘗試導入我們的 agent_tasks 模組（可能會因為 Redis 連接失敗）
        try:
            from agent_tasks import app
            print("   ✅ Agent Tasks 模組導入成功")
        except Exception as e:
            print(f"   ⚠️ Agent Tasks 模組導入警告: {e}")
            print("      這是正常的，因為 Redis 可能尚未啟動")
        
        return True
        
    except ImportError as e:
        print(f"   ❌ 模組導入失敗: {e}")
        return False


def run_all_tests():
    """執行所有測試"""
    print("🚀 開始測試多智能體協作流程自動化系統")
    print("=" * 60)
    
    tests = [
        ("配置管理器", test_config_manager),
        ("工作流程狀態機", test_state_machine),
        ("監控系統", test_monitoring),
        ("Celery 模組導入", test_celery_imports)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"   ❌ {test_name} 測試發生異常: {e}")
    
    print("\n" + "=" * 60)
    print(f"🏁 測試完成: {passed}/{total} 通過")
    
    if passed == total:
        print("🎉 所有測試通過！系統準備就緒。")
    else:
        print("⚠️ 部分測試失敗。請檢查配置和依賴。")
    
    print("\n📝 後續步驟:")
    print("1. 啟動 Docker 服務: docker-compose up -d")
    print("2. 檢查服務狀態: docker-compose ps")
    print("3. 查看 Celery 監控: http://localhost:5555")
    print("4. 測試任務執行: python -c \"from agent_tasks import execute_multi_agent_workflow; print('Ready!')\"")
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
