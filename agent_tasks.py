"""
Celery Tasks for Multi-Agent System
智能體系統的 Celery 任務模組
"""

import logging
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
from celery import Celery, Task
from celery.exceptions import Retry, WorkerLostError
from config_manager import get_config_manager
from workflow_state_machine import get_workflow_state_machine, TaskPriority, WorkflowTask, TaskState


logger = logging.getLogger(__name__)

# 取得配置管理器
config_manager = get_config_manager()
workflow_state_machine = get_workflow_state_machine()

# 初始化 Celery
try:
    celery_config = config_manager.get_celery_config()
    app = Celery('agent_tasks')
    
    # 配置 Celery
    app.conf.update(
        broker_url=celery_config.broker_url,
        result_backend=celery_config.result_backend,
        task_serializer=celery_config.task_serializer,
        accept_content=celery_config.accept_content,
        result_serializer=celery_config.result_serializer,
        timezone=celery_config.timezone,
        enable_utc=celery_config.enable_utc,
        task_routes=celery_config.task_routes,
        worker_concurrency=celery_config.worker_config.concurrency,
        worker_max_tasks_per_child=celery_config.worker_config.max_tasks_per_child,
        task_soft_time_limit=celery_config.worker_config.task_soft_time_limit,
        task_time_limit=celery_config.worker_config.task_time_limit,
        
        # 任務結果過期時間
        result_expires=3600,
        
        # 任務確認設置
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        
        # 錯誤處理
        task_reject_on_worker_lost=True,
        task_ignore_result=False,
        
        # 監控
        worker_send_task_events=True,
        task_send_sent_event=True,
    )
    
    logger.info("Celery app initialized successfully")
    
except Exception as e:
    logger.error(f"Failed to initialize Celery: {e}")
    # 創建一個基本的 Celery 實例作為備用
    app = Celery('agent_tasks', broker='redis://localhost:6379/0')


class BaseAgentTask(Task):
    """基礎智能體任務類別"""
    
    autoretry_for = (Exception,)
    retry_kwargs = {'max_retries': 3, 'countdown': 60}
    retry_backoff = True
    retry_backoff_max = 700
    retry_jitter = False

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """任務失敗時的回調"""
        logger.error(f"Task {task_id} failed: {exc}")
        
        # 更新狀態機中的任務狀態
        workflow_task_id = kwargs.get('workflow_task_id')
        step_name = kwargs.get('step_name')
        
        if workflow_task_id and step_name:
            workflow_state_machine.execute_workflow_step(
                workflow_task_id, step_name, error=str(exc)
            )

    def on_success(self, retval, task_id, args, kwargs):
        """任務成功時的回調"""
        logger.info(f"Task {task_id} completed successfully")
        
        # 更新狀態機中的任務狀態
        workflow_task_id = kwargs.get('workflow_task_id')
        step_name = kwargs.get('step_name')
        
        if workflow_task_id and step_name:
            workflow_state_machine.execute_workflow_step(
                workflow_task_id, step_name, execution_result=retval
            )

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """任務重試時的回調"""
        logger.warning(f"Task {task_id} retrying due to: {exc}")


@app.task(bind=True, base=BaseAgentTask)
def execute_agent_task(self, agent_name: str, content: str, workflow_task_id: str, 
                      step_name: str, agent_config: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    執行單個智能體任務
    
    Args:
        agent_name: 智能體名稱
        content: 輸入內容
        workflow_task_id: 工作流程任務ID
        step_name: 步驟名稱
        agent_config: 智能體配置
        
    Returns:
        Dict: 執行結果
    """
    try:
        logger.info(f"Executing agent task: {agent_name} for workflow {workflow_task_id}, step {step_name}")
        
        # 記錄任務開始時間
        start_time = datetime.utcnow()
        
        # 這裡會整合實際的智能體執行邏輯
        # 目前先模擬執行
        result = {
            "agent": agent_name,
            "step": step_name,
            "content": f"Processed by {agent_name}: {content}",
            "timestamp": start_time.isoformat(),
            "task_id": self.request.id,
            "workflow_task_id": workflow_task_id,
            "status": "completed"
        }
        
        # 模擬處理時間
        import time
        time.sleep(2)  # 模擬 2 秒處理時間
        
        end_time = datetime.utcnow()
        result["duration_seconds"] = (end_time - start_time).total_seconds()
        
        logger.info(f"Agent task {agent_name} completed for workflow {workflow_task_id}")
        return result
        
    except Exception as e:
        logger.error(f"Error executing agent task {agent_name}: {e}")
        raise self.retry(exc=e)


@app.task(bind=True, base=BaseAgentTask)
def execute_multi_agent_workflow(self, user_input: str, workflow_name: str = "default", 
                                priority: str = "normal", workflow_task_id_from_api: Optional[str] = None) -> Dict[str, Any]:
    """
    執行多智能體工作流程
    
    Args:
        user_input: 使用者輸入
        workflow_name: 工作流程名稱
        priority: 任務優先級
        workflow_task_id_from_api: (Optional) 從 API 傳入的任務 ID
        
    Returns:
        Dict: 工作流程執行結果
    """
    workflow_task: Optional[WorkflowTask] = None
    try:
        logger.info(f"Starting execute_multi_agent_workflow with user_input='{user_input}', workflow_name='{workflow_name}', priority='{priority}', workflow_task_id_from_api='{workflow_task_id_from_api}', celery_task_id='{self.request.id}'")
        
        if workflow_task_id_from_api:
            logger.info(f"Executing multi-agent workflow: {workflow_name} for existing task ID: {workflow_task_id_from_api}")
            workflow_task = workflow_state_machine.get_task(workflow_task_id_from_api)
            if not workflow_task:
                logger.error(f"Workflow task {workflow_task_id_from_api} not found in state machine.")
                raise ValueError(f"Task {workflow_task_id_from_api} not found.")
            
            # 確保 Celery 任務 ID 已關聯
            if 'celery_task_id' not in workflow_task.metadata or workflow_task.metadata['celery_task_id'] != self.request.id:
                 workflow_task.metadata['celery_task_id'] = self.request.id
        else:
            logger.warning(f"No workflow_task_id_from_api provided for workflow {workflow_name}, creating a new task.")
            task_id = str(uuid.uuid4()) 
            task_priority = TaskPriority(priority) if priority in [p.value for p in TaskPriority] else TaskPriority.NORMAL
            workflow_task = workflow_state_machine.create_task(
                task_id=task_id,
                workflow_name=workflow_name,
                user_input=user_input,
                priority=task_priority,
                celery_task_id=self.request.id
            )
            # 新創建的任務處於 IDLE 狀態，需要轉換到 QUEUED
            workflow_state_machine.start_task(task_id) # IDLE -> QUEUED

        if not workflow_task: # Should not happen if logic above is correct
            raise Exception("Workflow task object is not initialized.")

        # 確保任務處於 QUEUED 狀態，然後轉換到 RUNNING
        if workflow_task.state == TaskState.QUEUED.value:
             workflow_task.begin_execution() # QUEUED -> RUNNING
        elif workflow_task.state != TaskState.RUNNING.value:
            logger.error(f"Task {workflow_task.task_id} is in unexpected state {workflow_task.state} before beginning execution.")
            workflow_task.error_message = f"Unexpected state {workflow_task.state} at Celery task start."
            workflow_task.fail_task() # This will trigger on_failure if state allows
            raise ValueError(f"Task {workflow_task.task_id} in unexpected state {workflow_task.state}")
        
        logger.info(f"Workflow task {workflow_task.task_id} is now in state: {workflow_task.state}")

        # 取得工作流程配置
        logger.info(f"Getting workflow config for workflow: {workflow_name}")
        workflow_config = config_manager.get_workflow_config(workflow_name)
        if not workflow_config:
            logger.error(f"Workflow config not found for workflow: {workflow_name}")
            raise ValueError(f"Workflow {workflow_name} not found")
        
        logger.info(f"Workflow config found with {len(workflow_config.steps)} steps: {[step.name for step in workflow_config.steps]}")
        
        # 執行工作流程步驟
        results = []
        
        for step in workflow_config.steps:
            logger.info(f"Processing step: {step.name} with agent: {step.agent}")
            
            # 檢查依賴是否滿足
            dependencies_met = all(dep in workflow_task.completed_steps for dep in step.dependencies)
            logger.info(f"Step {step.name} dependencies check: {step.dependencies} -> {'met' if dependencies_met else 'not met'}")
            
            if not dependencies_met:
                logger.info(f"Step {step.name} dependencies not met, waiting...")
                workflow_task.wait_for_dependency()
                continue
            
            # 取得智能體配置
            agent_config = config_manager.get_agent_config(step.agent)
            if not agent_config:
                raise ValueError(f"Agent {step.agent} not found")
            
            # 執行智能體任務
            try:
                # 這裡應該調用實際的智能體執行邏輯
                # 目前先使用模擬結果
                step_result = {
                    "step_name": step.name,
                    "agent": step.agent,
                    "result": f"Step {step.name} completed by {step.agent}",
                    "timestamp": datetime.utcnow().isoformat(),
                    "required": step.required,
                    "dependencies": step.dependencies
                }
                
                results.append(step_result)
                workflow_task.completed_steps.append(step.name)
                
                logger.info(f"Step {step.name} completed successfully")
                
            except Exception as step_error:
                logger.error(f"Step {step.name} failed: {step_error}")
                
                if step.retry_on_failure and workflow_task.retry_count < workflow_task.max_retries:
                    workflow_task.retry_count += 1
                    logger.info(f"Retrying step {step.name} (attempt {workflow_task.retry_count})")
                    continue
                else:
                    if step.required:
                        # 必要步驟失敗，整個工作流程失敗
                        workflow_task.error_message = str(step_error)
                        workflow_task.fail_task()
                        raise step_error
                    else:
                        # 可選步驟失敗，繼續執行
                        workflow_task.failed_steps.append(step.name)
                        logger.warning(f"Optional step {step.name} failed, continuing...")
        
        # 完成工作流程
        final_result = {
            "workflow_task_id": workflow_task.task_id, # Use actual task_id
            "workflow_name": workflow_name,
            "user_input": user_input,
            "results": results,
            "completed_steps": workflow_task.completed_steps,
            "failed_steps": workflow_task.failed_steps,
            "total_steps": len(workflow_config.steps),
            "success_rate": len(workflow_task.completed_steps) / len(workflow_config.steps),
            "execution_time": (datetime.utcnow() - workflow_task.created_at).total_seconds(),
            "celery_task_id": self.request.id,
            "status": "completed"
        }
        
        workflow_task.final_result = final_result
        workflow_task.complete_task()
        
        logger.info(f"Multi-agent workflow {workflow_name} completed successfully")
        return final_result
        
    except Exception as e:
        logger.error(f"Error executing multi-agent workflow: {e}")
        logger.exception("Full exception details:")
        
        # 更新任務狀態為失敗
        if workflow_task is not None:
            try:
                workflow_task.error_message = str(e)
                workflow_task.fail_task()
                logger.info(f"Task {workflow_task.task_id} marked as failed")
            except Exception as state_error:
                logger.error(f"Failed to update task state: {state_error}")
        
        raise self.retry(exc=e)


@app.task(bind=True)
def fetch_data_task(self, url: str, workflow_task_id: str, step_name: str) -> Dict[str, Any]:
    """
    數據獲取任務（fetcher 智能體）
    
    Args:
        url: 要獲取的 URL
        workflow_task_id: 工作流程任務ID
        step_name: 步驟名稱
        
    Returns:
        Dict: 獲取結果
    """
    try:
        logger.info(f"Fetching data from {url}")
        
        # 這裡應該整合實際的數據獲取邏輯
        # 目前先模擬
        result = {
            "url": url,
            "content": f"Mock content from {url}",
            "timestamp": datetime.utcnow().isoformat(),
            "status": "success"
        }
        
        logger.info(f"Data fetched successfully from {url}")
        return result
        
    except Exception as e:
        logger.error(f"Error fetching data from {url}: {e}")
        raise


@app.task(bind=True)
def summarize_content_task(self, content: str, workflow_task_id: str, step_name: str) -> Dict[str, Any]:
    """
    內容摘要任務（summarizer 智能體）
    
    Args:
        content: 要摘要的內容
        workflow_task_id: 工作流程任務ID
        step_name: 步驟名稱
        
    Returns:
        Dict: 摘要結果
    """
    try:
        logger.info(f"Summarizing content")
        
        # 這裡應該整合實際的摘要邏輯
        # 目前先模擬
        result = {
            "original_content": content,
            "summary": f"Summary of: {content[:100]}...",
            "word_count": len(content.split()),
            "summary_ratio": 0.3,
            "timestamp": datetime.utcnow().isoformat(),
            "status": "success"
        }
        
        logger.info(f"Content summarized successfully")
        return result
        
    except Exception as e:
        logger.error(f"Error summarizing content: {e}")
        raise


@app.task(bind=True)
def analyze_data_task(self, data: Dict[str, Any], workflow_task_id: str, step_name: str) -> Dict[str, Any]:
    """
    數據分析任務（analyzer 智能體）
    
    Args:
        data: 要分析的數據
        workflow_task_id: 工作流程任務ID
        step_name: 步驟名稱
        
    Returns:
        Dict: 分析結果
    """
    try:
        logger.info(f"Analyzing data")
        
        # 這裡應該整合實際的分析邏輯
        # 目前先模擬
        result = {
            "input_data": data,
            "analysis": {
                "patterns": ["pattern1", "pattern2"],
                "trends": ["trend1", "trend2"],
                "insights": ["insight1", "insight2"]
            },
            "confidence_score": 0.85,
            "timestamp": datetime.utcnow().isoformat(),
            "status": "success"
        }
        
        logger.info(f"Data analyzed successfully")
        return result
        
    except Exception as e:
        logger.error(f"Error analyzing data: {e}")
        raise


@app.task(bind=True)
def coordinate_workflow_task(self, workflow_results: List[Dict[str, Any]], 
                           workflow_task_id: str, step_name: str) -> Dict[str, Any]:
    """
    工作流程協調任務（coordinator 智能體）
    
    Args:
        workflow_results: 工作流程結果列表
        workflow_task_id: 工作流程任務ID
        step_name: 步驟名稱
        
    Returns:
        Dict: 協調結果
    """
    try:
        logger.info(f"Coordinating workflow")
        
        # 這裡應該整合實際的協調邏輯
        # 目前先模擬
        result = {
            "workflow_results": workflow_results,
            "coordination": {
                "total_steps": len(workflow_results),
                "successful_steps": len([r for r in workflow_results if r.get("status") == "success"]),
                "quality_score": 0.9,
                "recommendations": ["rec1", "rec2"]
            },
            "timestamp": datetime.utcnow().isoformat(),
            "status": "success"
        }
        
        logger.info(f"Workflow coordinated successfully")
        return result
        
    except Exception as e:
        logger.error(f"Error coordinating workflow: {e}")
        raise


@app.task(bind=True)
def generate_response_task(self, processed_data: Dict[str, Any], 
                         workflow_task_id: str, step_name: str) -> Dict[str, Any]:
    """
    回應生成任務（responder 智能體）
    
    Args:
        processed_data: 處理過的數據
        workflow_task_id: 工作流程任務ID
        step_name: 步驟名稱
        
    Returns:
        Dict: 回應結果
    """
    try:
        logger.info(f"Generating response")
        
        # 這裡應該整合實際的回應生成邏輯
        # 目前先模擬
        result = {
            "processed_data": processed_data,
            "final_response": "This is a comprehensive response based on the multi-agent collaboration.",
            "response_metadata": {
                "word_count": 12,
                "confidence": 0.95,
                "sources": ["fetcher", "summarizer", "analyzer", "coordinator"]
            },
            "timestamp": datetime.utcnow().isoformat(),
            "status": "success"
        }
        
        logger.info(f"Response generated successfully")
        return result
        
    except Exception as e:
        logger.error(f"Error generating response: {e}")
        raise


@app.task
def cleanup_old_tasks():
    """清理舊任務的定期任務"""
    try:
        logger.info("Starting cleanup of old tasks")
        
        # 清理狀態機中的舊任務
        workflow_state_machine.cleanup_completed_tasks(max_age_hours=24)
        
        # 這裡可以添加其他清理邏輯，例如清理 Redis 中的結果等
        
        logger.info("Cleanup completed successfully")
        return {"status": "success", "timestamp": datetime.utcnow().isoformat()}
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        raise


@app.task
def health_check():
    """健康檢查任務"""
    try:
        # 檢查配置管理器
        config_manager.get_config()
        
        # 檢查狀態機
        stats = workflow_state_machine.get_task_statistics()
        
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "task_statistics": stats,
            "celery_active": True
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


# 定期任務設置
app.conf.beat_schedule = {
    'cleanup-old-tasks': {
        'task': 'agent_tasks.cleanup_old_tasks',
        'schedule': 3600.0,  # 每小時執行一次
    },
    'health-check': {
        'task': 'agent_tasks.health_check',
        'schedule': 300.0,  # 每 5 分鐘執行一次
    },
}

if __name__ == '__main__':
    app.start()
