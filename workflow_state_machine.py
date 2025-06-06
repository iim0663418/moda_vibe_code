"""
Workflow State Machine for Multi-Agent System
智能體協作流程狀態機模組
"""

import logging
import asyncio
import json # For Redis serialization
import redis # For Redis persistence
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import TYPE_CHECKING
from transitions import Machine
from config_manager import get_config_manager, WorkflowStep, Workflow

if TYPE_CHECKING:
    from .workflow_state_machine import WorkflowStateMachine # Forward declaration
    from celery.result import AsyncResult # For Celery task result

REDIS_HOST = "redis"  # Docker service name
REDIS_PORT = 6379
REDIS_DB = 0
REDIS_TASK_PREFIX = "workflow_task:"
REDIS_TASK_TTL_SECONDS = 24 * 60 * 60  # 24 hours

logger = logging.getLogger(__name__)


class TaskState(str, Enum):
    """任務狀態枚舉"""
    IDLE = "idle"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_FOR_DEPENDENCY = "waiting_for_dependency"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"

# Helper function for datetime serialization/deserialization
def datetime_to_iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None

def iso_to_datetime(iso_str: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(iso_str) if iso_str else None

class TaskPriority(str, Enum):
    """任務優先級"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class TaskExecution:
    """任務執行記錄"""
    task_id: str
    agent_name: str
    step_name: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    retry_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowTask:
    """工作流程任務"""
    task_id: str
    workflow_name: str
    user_input: str
    state: str = TaskState.IDLE.value
    priority: TaskPriority = TaskPriority.NORMAL
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    
    # 執行追蹤
    current_step: Optional[str] = None
    completed_steps: List[str] = field(default_factory=list)
    failed_steps: List[str] = field(default_factory=list)
    step_executions: Dict[str, TaskExecution] = field(default_factory=dict)
    
    # 結果
    final_result: Optional[Any] = None
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)
   
    # 元資料
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Machine instance will be attached after creation/loading
    machine: Optional[Machine] = field(default=None, repr=False, compare=False, init=False)

    def on_task_queued(self):
        # Logic handled by WorkflowStateMachine
        pass

    def on_task_started(self):
        # Logic handled by WorkflowStateMachine
        pass

    def on_task_waiting(self):
        # Logic handled by WorkflowStateMachine
        pass

    def on_task_resumed(self):
        # Logic handled by WorkflowStateMachine
        pass

    def on_task_completed(self):
        # Logic handled by WorkflowStateMachine
        pass

    def on_task_failed(self):
        # Logic handled by WorkflowStateMachine
        pass

    def on_task_retry(self):
        # Logic handled by WorkflowStateMachine
        pass

    def on_task_cancelled(self):
        # Logic handled by WorkflowStateMachine
        pass

    def on_task_reset(self):
        # Logic handled by WorkflowStateMachine
        pass
            
    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries

    def to_dict(self) -> Dict[str, Any]:
        """將任務物件序列化為字典，以便存儲到 Redis"""
        # Manually construct the dictionary to exclude the 'machine' attribute
        # and other non-serializable fields if any.
        data = {
            f.name: getattr(self, f.name)
            for f in self.__dataclass_fields__.values()
            if f.name != 'machine'  # Exclude the machine attribute
        }
        
        # Convert datetime objects to ISO format strings
        data['created_at'] = datetime_to_iso(self.created_at)
        data['started_at'] = datetime_to_iso(self.started_at)
        data['completed_at'] = datetime_to_iso(self.completed_at)
        
        # Serialize TaskPriority enum to its value
        if isinstance(self.priority, TaskPriority):
            data['priority'] = self.priority.value

        # Serialize TaskExecution objects within step_executions
        serialized_step_executions = {}
        if 'step_executions' in data and isinstance(data['step_executions'], dict):
            for step_name, exec_obj in data['step_executions'].items():
                if isinstance(exec_obj, TaskExecution):
                    exec_dict = asdict(exec_obj)
                    exec_dict['start_time'] = datetime_to_iso(exec_obj.start_time)
                    exec_dict['end_time'] = datetime_to_iso(exec_obj.end_time)
                    serialized_step_executions[step_name] = exec_dict
                elif isinstance(exec_obj, dict): # If already a dict (e.g. from_dict)
                    # Ensure datetimes within the dict are converted to ISO strings
                    exec_obj['start_time'] = datetime_to_iso(iso_to_datetime(exec_obj.get('start_time')))
                    exec_obj['end_time'] = datetime_to_iso(iso_to_datetime(exec_obj.get('end_time')))
                    serialized_step_executions[step_name] = exec_obj
            data['step_executions'] = serialized_step_executions


        # Remove machine as it's not serializable and recreated on load
        if 'machine' in data:
            del data['machine']
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkflowTask':
        """從字典反序列化任務物件"""
        data['created_at'] = iso_to_datetime(data.get('created_at'))
        data['started_at'] = iso_to_datetime(data.get('started_at'))
        data['completed_at'] = iso_to_datetime(data.get('completed_at'))
        
        if isinstance(data.get('priority'), str):
            try:
                data['priority'] = TaskPriority(data['priority'])
            except ValueError:
                logger.warning(f"Invalid priority value '{data['priority']}' in stored task, defaulting to NORMAL.")
                data['priority'] = TaskPriority.NORMAL

        # Deserialize TaskExecution objects
        deserialized_step_executions = {}
        if 'step_executions' in data and isinstance(data['step_executions'], dict):
            for step_name, exec_data in data['step_executions'].items():
                if isinstance(exec_data, dict):
                    exec_data['start_time'] = iso_to_datetime(exec_data.get('start_time'))
                    exec_data['end_time'] = iso_to_datetime(exec_data.get('end_time'))
                    deserialized_step_executions[step_name] = TaskExecution(**exec_data)
            data['step_executions'] = deserialized_step_executions

        data.pop('machine', None) # Machine is recreated
        return cls(**data)

class WorkflowStateMachine:
    """工作流程狀態機"""
    
    def __init__(self):
        """初始化狀態機"""
        self.config_manager = get_config_manager()
        try:
            self.redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=False)
            self.redis_client.ping() 
            logger.info(f"Successfully connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
        except redis.exceptions.ConnectionError as e:
            logger.error(f"Failed to connect to Redis at {REDIS_HOST}:{REDIS_PORT}: {e}")
            self.redis_client = None
        
        self.states = [state.value for state in TaskState]
        # Define transitions with lambda functions for 'after' callbacks
        # This ensures that the methods on WorkflowStateMachine are called with the WorkflowTask instance (event.model)
        self.transitions = [
            {'trigger': 'start_task', 'source': TaskState.IDLE.value, 'dest': TaskState.QUEUED.value, 
             'after': lambda event: self.on_task_queued(event.model)},
            {'trigger': 'begin_execution', 'source': TaskState.QUEUED.value, 'dest': TaskState.RUNNING.value,
             'after': lambda event: self.on_task_started(event.model)},
            {'trigger': 'wait_for_dependency', 'source': TaskState.RUNNING.value, 'dest': TaskState.WAITING_FOR_DEPENDENCY.value,
             'after': lambda event: self.on_task_waiting(event.model)},
            {'trigger': 'resume_execution', 'source': TaskState.WAITING_FOR_DEPENDENCY.value, 'dest': TaskState.RUNNING.value,
             'after': lambda event: self.on_task_resumed(event.model)},
            {'trigger': 'complete_task', 'source': [TaskState.RUNNING.value, TaskState.RETRYING.value], 'dest': TaskState.COMPLETED.value,
             'after': lambda event: self.on_task_completed(event.model)},
            {'trigger': 'fail_task', 'source': [TaskState.RUNNING.value, TaskState.WAITING_FOR_DEPENDENCY.value, TaskState.RETRYING.value, TaskState.QUEUED.value], 
             'dest': TaskState.FAILED.value, 'after': lambda event: self.on_task_failed(event.model)},
            {'trigger': 'retry_task', 'source': TaskState.FAILED.value, 'dest': TaskState.RETRYING.value,
             'conditions': 'can_retry', 'after': lambda event: self.on_task_retry(event.model)}, # Note: can_retry is a method on WorkflowTask model
            {'trigger': 'cancel_task', 'source': [TaskState.QUEUED.value, TaskState.RUNNING.value, TaskState.WAITING_FOR_DEPENDENCY.value], 
             'dest': TaskState.CANCELLED.value, 'after': lambda event: self.on_task_cancelled(event.model)},
            {'trigger': 'reset_task', 'source': [TaskState.COMPLETED.value, TaskState.FAILED.value, TaskState.CANCELLED.value], 
             'dest': TaskState.IDLE.value, 'after': lambda event: self.on_task_reset(event.model)}
        ]
        
        self.callbacks: Dict[str, List[Callable]] = {
            'on_task_queued': [],
            'on_task_started': [],
            'on_task_waiting': [],
            'on_task_resumed': [],
            'on_task_completed': [],
            'on_task_failed': [],
            'on_task_retry': [],
            'on_task_cancelled': [],
            'on_task_reset': []
        }

    def _handle_after_state_change(self, event_data):
        """
        Wrapper for after_state_change callback to ensure event_data is passed correctly.
        This method is called by the transitions library and then calls the actual saving logic.
        """
        logger.debug(f"_handle_after_state_change called with event_data type: {type(event_data)}")
        self._save_task_to_redis(event_data)

    def _save_task_to_redis(self, event_data): # Changed parameter name
        """將任務狀態保存到 Redis。接收 EventData 物件。"""
        if not self.redis_client:
            logger.error("Redis client not available. Cannot save task.")
            return

        # Extract the WorkflowTask instance from event_data
        task: Optional[WorkflowTask] = None
        
        # Log the type and content of event_data for detailed debugging
        logger.debug(f"_save_task_to_redis received event_data of type: {type(event_data)}")

        # First, check if event_data itself is a WorkflowTask instance
        if isinstance(event_data, WorkflowTask):
            task = event_data
            logger.debug(f"event_data is a WorkflowTask. Task ID: {task.task_id if task else 'None'}")
        # Next, check if event_data is an object (like EventData from transitions)
        # that has a 'model' attribute which is a WorkflowTask instance
        elif hasattr(event_data, 'model') and isinstance(event_data.model, WorkflowTask):
            task = event_data.model
            logger.debug(f"Extracted task from event_data.model. Task ID: {task.task_id if task else 'None'}")
        # If neither of the above, then we cannot extract the task
        else:
            # Log detailed information if extraction fails
            details = ""
            if hasattr(event_data, 'model'):
                details = f"event_data has 'model' attribute of type {type(event_data.model)}."
            # It's useful to know if it's an EventData object but with an invalid model
            elif type(event_data).__name__ == 'EventData': 
                details = "event_data is an EventData object, but its 'model' is not a WorkflowTask or is missing."
            else:
                details = "event_data does not appear to be a WorkflowTask or a standard EventData object with a 'model' attribute."
            logger.error(f"Could not extract WorkflowTask. event_data type: {type(event_data)}. {details} Value (first 200 chars): {str(event_data)[:200]}")
            return # Stop if task cannot be extracted

        if not task:
            # This condition should ideally be unreachable if the logic above is complete and correct.
            # If reached, it implies an unexpected state or a flaw in the extraction logic not caught by the specific checks.
            logger.error(f"Critical: Task is None after extraction attempt from event_data (type: {type(event_data)}). This indicates an issue in the extraction logic itself or unexpected event_data content.")
            return

        try:
            task_key = f"{REDIS_TASK_PREFIX}{task.task_id}"
            task_data_dict = task.to_dict()
            task_data_json_str = json.dumps(task_data_dict)
            self.redis_client.set(task_key, task_data_json_str, ex=REDIS_TASK_TTL_SECONDS)
            logger.debug(f"Saved/Updated task {task.task_id} to Redis. Key: {task_key}, Data: {task_data_json_str[:200]}...") # Log first 200 chars
        except Exception as e:
            logger.error(f"Failed to save task {task.task_id} to Redis: {e}", exc_info=True)


    def create_task(self, task_id: str, workflow_name: str, user_input: str, 
                   priority: TaskPriority = TaskPriority.NORMAL, **metadata) -> WorkflowTask:
        """創建新任務並保存到 Redis"""
        logger.debug(f"Attempting to create task {task_id} with workflow {workflow_name}")
        if self.get_task(task_id): # Check Redis first
            logger.warning(f"Task {task_id} already exists in Redis, not creating new one.")
            raise ValueError(f"Task {task_id} already exists in Redis")
        
        workflow = self.config_manager.get_workflow_config(workflow_name)
        if not workflow:
            logger.error(f"Workflow {workflow_name} not found for task {task_id}")
            raise ValueError(f"Workflow {workflow_name} not found")
        
        task = WorkflowTask(
            task_id=task_id,
            workflow_name=workflow_name,
            user_input=user_input,
            priority=priority,
            metadata=metadata
        )
        
        task.machine = Machine(
            model=task,
            states=self.states,
            transitions=self.transitions,
            initial=TaskState.IDLE.value,
            ignore_invalid_triggers=True,
            after_state_change=self._handle_after_state_change,
            send_event=True  # Explicitly ensure EventData is sent to callbacks
        )
        
        self._save_task_to_redis(task) 
        logger.info(f"Created task {task_id} with workflow {workflow_name} and saved to Redis")
        return task

    def get_task(self, task_id: str) -> Optional[WorkflowTask]:
        """從 Redis 取得任務"""
        if not self.redis_client:
            logger.error("Redis client not available. Cannot get task.")
            return None
        try:
            task_key = f"{REDIS_TASK_PREFIX}{task_id}"
            logger.debug(f"Attempting to get task from Redis. Key: {task_key}")
            task_data_json = self.redis_client.get(task_key)
            if task_data_json:
                logger.debug(f"Raw data for {task_id}: {task_data_json[:200]}...") # Log raw data
                task_data_dict = json.loads(task_data_json.decode('utf-8')) # Ensure decoding
                task = WorkflowTask.from_dict(task_data_dict)
                task.machine = Machine(
                    model=task,
                    states=self.states,
                    transitions=self.transitions,
                    initial=task.state, 
                    ignore_invalid_triggers=True,
                    after_state_change=self._handle_after_state_change,
                    send_event=True  # Explicitly ensure EventData is sent to callbacks
                )
                logger.debug(f"Loaded task {task_id} from Redis. State: {task.state}")
                return task
            logger.debug(f"Task {task_id} not found in Redis.")
            return None
        except Exception as e:
            logger.error(f"Failed to get task {task_id} from Redis: {e}", exc_info=True)
            return None

    def start_task(self, task_id: str) -> bool:
        """啟動任務"""
        task = self.get_task(task_id)
        if not task:
            logger.error(f"Task {task_id} not found")
            return False
        
        try:
            if task.state == TaskState.IDLE.value: # Ensure it's idle before starting
                task.start_task() # This will trigger 'on_task_queued' and save to Redis via after_state_change
                logger.info(f"Task {task_id} triggered to start.")
                return True
            else:
                logger.warning(f"Task {task_id} is not in IDLE state, cannot start. Current state: {task.state}")
                return False
        except Exception as e:
            logger.error(f"Failed to start task {task_id}: {e}", exc_info=True)
            return False

    def execute_workflow_step(self, task_id: str, step_name: str, 
                            execution_result: Any = None, error: str = None) -> bool:
        """執行工作流程步驟並更新 Redis"""
        task = self.get_task(task_id)
        if not task:
            logger.error(f"Task {task_id} not found for execute_workflow_step")
            return False
        
        workflow = self.config_manager.get_workflow_config(task.workflow_name)
        if not workflow:
            logger.error(f"Workflow {task.workflow_name} not found for task {task_id}")
            return False
        
        step_config = next((s for s in workflow.steps if s.name == step_name), None)
        if not step_config:
            logger.error(f"Step {step_name} not found in workflow {task.workflow_name}")
            return False
        
        execution = TaskExecution(
            task_id=task_id, agent_name=step_config.agent, step_name=step_name,
            start_time=datetime.utcnow(), result=execution_result, error=error
        )
        execution.end_time = datetime.utcnow()
        
        task.step_executions[step_name] = execution
        
        if error:
            task.failed_steps.append(step_name)
            if step_config.retry_on_failure and task.can_retry():
                task.retry_count += 1
                execution.retry_count = task.retry_count
                logger.warning(f"Step {step_name} for task {task_id} failed, retrying (attempt {task.retry_count})")
                # State transition to RETRYING should be handled by Celery task calling retry_task
            else:
                task.error_message = error
                if hasattr(task, 'fail_task') and callable(task.fail_task):
                    task.fail_task() # Triggers on_task_failed and saves
        else:
            task.completed_steps.append(step_name)
            task.current_step = step_name
            if self.is_workflow_completed(task):
                task.final_result = execution_result # Or aggregate results
                if hasattr(task, 'complete_task') and callable(task.complete_task):
                    task.complete_task() # Triggers on_task_completed and saves
        
        self._save_task_to_redis(task) # Ensure state is saved after manual updates
        logger.info(f"Task {task_id} step {step_name} executed. Status: {'FAILED' if error else 'COMPLETED'}")
        return True

    def is_workflow_completed(self, task: WorkflowTask) -> bool:
        """檢查工作流程是否完成"""
        workflow = self.config_manager.get_workflow_config(task.workflow_name)
        if not workflow: 
            logger.warning(f"Workflow config for {task.workflow_name} not found when checking completion.")
            return False
        required_steps = [s.name for s in workflow.steps if s.required]
        is_completed = all(rs in task.completed_steps for rs in required_steps)
        logger.debug(f"Task {task.task_id} completion check: {is_completed}. Completed steps: {task.completed_steps}, Required: {required_steps}")
        return is_completed

    def get_next_step(self, task: WorkflowTask) -> Optional[WorkflowStep]:
        """取得下一個要執行的步驟"""
        workflow = self.config_manager.get_workflow_config(task.workflow_name)
        if not workflow: 
            logger.warning(f"Workflow config for {task.workflow_name} not found when getting next step.")
            return None
        for step in workflow.steps:
            if step.name in task.completed_steps: continue
            if all(dep in task.completed_steps for dep in step.dependencies):
                logger.debug(f"Next step for task {task.task_id}: {step.name}")
                return step
        logger.debug(f"No next step found for task {task.task_id}. All dependencies met or no more steps.")
        return None

    def get_all_tasks(self) -> List[WorkflowTask]:
        """從 Redis 取得所有任務"""
        if not self.redis_client:
            logger.error("Redis client not available. Cannot get all tasks.")
            return []
        
        all_tasks: List[WorkflowTask] = []
        try:
            logger.debug(f"Scanning Redis for keys matching {REDIS_TASK_PREFIX}*")
            keys_found = 0
            for key_bytes in self.redis_client.scan_iter(match=f"{REDIS_TASK_PREFIX}*"):
                keys_found += 1
                task_key_str = key_bytes.decode('utf-8')
                task_id = task_key_str.replace(REDIS_TASK_PREFIX, "")
                logger.debug(f"Found key: {task_key_str}, attempting to load task_id: {task_id}")
                task = self.get_task(task_id) # Use existing get_task to rehydrate
                if task:
                    all_tasks.append(task)
                else:
                    logger.warning(f"Failed to load task for key: {task_key_str}. It might be corrupted or expired.")
            logger.debug(f"Finished scanning Redis. Found {keys_found} keys, loaded {len(all_tasks)} tasks.")
        except Exception as e:
            logger.error(f"Failed to retrieve all tasks from Redis: {e}", exc_info=True)
        return all_tasks

    def can_retry(self, task: WorkflowTask) -> bool:
        """檢查任務是否可以重試"""
        can_retry_result = task.retry_count < task.max_retries
        logger.debug(f"Task {task.task_id} can retry: {can_retry_result} (current retries: {task.retry_count}, max: {task.max_retries})")
        return can_retry_result

    def get_task_statistics(self) -> Dict[str, Any]:
        """從 Redis 取得任務統計資訊"""
        if not self.redis_client:
            logger.error("Redis client not available. Cannot get task statistics.")
            return {} # Or some default error structure

        stats = {'total_tasks': 0, 'active_tasks': 0, 'by_state': {}, 'by_priority': {}, 'by_workflow': {}}
        
        all_tasks = self.get_all_tasks() # Use the new method
        stats['total_tasks'] = len(all_tasks)

        for task in all_tasks:
            stats['by_state'][task.state] = stats['by_state'].get(task.state, 0) + 1
            stats['by_priority'][task.priority.value] = stats['by_priority'].get(task.priority.value, 0) + 1
            stats['by_workflow'][task.workflow_name] = stats['by_workflow'].get(task.workflow_name, 0) + 1
            if task.state not in [TaskState.COMPLETED.value, TaskState.FAILED.value, TaskState.CANCELLED.value]:
                stats['active_tasks'] +=1
        logger.debug(f"Task statistics: {stats}")
        return stats

    def cleanup_completed_tasks(self, max_age_hours: int = 24):
        """從 Redis 清理已完成的舊任務"""
        if not self.redis_client:
            logger.error("Redis client not available. Cannot cleanup tasks.")
            return

        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        logger.info(f"Starting cleanup of tasks older than {cutoff_time.isoformat()}")
        task_keys = [key.decode('utf-8') for key in self.redis_client.scan_iter(match=f"{REDIS_TASK_PREFIX}*")]
        cleaned_count = 0

        for task_key in task_keys:
            task_id = task_key.replace(REDIS_TASK_PREFIX, "")
            task_data_json = self.redis_client.get(task_key)
            if task_data_json:
                try:
                    task_data_dict = json.loads(task_data_json.decode('utf-8'))
                    task_state = task_data_dict.get('state')
                    completed_at_str = task_data_dict.get('completed_at')
                    
                    if (task_state in [TaskState.COMPLETED.value, TaskState.FAILED.value, TaskState.CANCELLED.value] 
                        and completed_at_str):
                        completed_at = iso_to_datetime(completed_at_str)
                        if completed_at and completed_at < cutoff_time:
                            self.redis_client.delete(task_key)
                            cleaned_count += 1
                            logger.info(f"Cleaned up old task {task_id} from Redis")
                except Exception as e:
                    logger.error(f"Error processing task {task_id} during cleanup: {e}", exc_info=True)
        logger.info(f"Finished cleanup. Cleaned {cleaned_count} tasks.")
        
    def register_callback(self, event: str, callback: Callable):
        """註冊事件回調函數"""
        if event in self.callbacks:
            self.callbacks[event].append(callback)
            logger.debug(f"Registered callback for event: {event}")

    # 狀態轉換回調函數 (由 Machine 的 after_state_change 觸發 _save_task_to_redis)
    # 這些 on_task_* 方法主要用於觸發外部回調，而不是直接修改任務狀態後保存，
    # 因為狀態機的 after_state_change hook 已經處理了保存。
    def on_task_queued(self, task: WorkflowTask):
        """任務進入隊列時的回調"""
        # task.started_at is set in on_task_started
        logger.info(f"Task {task.task_id} (state: {task.state}) queued, preparing to dispatch Celery task...")
        # _save_task_to_redis is called by Machine

        from agent_tasks import execute_multi_agent_workflow 
        
        celery_task_kwargs = {
            'user_input': task.user_input,
            'workflow_name': task.workflow_name,
            'priority': task.priority.value, # Ensure enum value is passed
            'workflow_task_id_from_api': task.task_id
        }
        
        try:
            celery_task_result: Optional[AsyncResult] = execute_multi_agent_workflow.apply_async(
                kwargs=celery_task_kwargs,
                task_id=f"celery_{task.task_id}"
            )
            if celery_task_result and celery_task_result.id:
                task.metadata['celery_task_id'] = celery_task_result.id
                logger.info(f"Celery task {celery_task_result.id} dispatched for workflow {task.task_id}. Celery state: {celery_task_result.state}")
                self._save_task_to_redis(task) # Save metadata update
            else:
                logger.error(f"Failed to dispatch Celery task for workflow {task.task_id}. 'apply_async' returned None or no ID.")
                if hasattr(task, 'fail_task') and callable(task.fail_task):
                    task.fail_task(error_message="Celery dispatch error: apply_async returned no ID") 
        except Exception as e:
            logger.error(f"Exception during Celery task dispatch for workflow {task.task_id}: {e}", exc_info=True)
            if hasattr(task, 'fail_task') and callable(task.fail_task):
                task.fail_task(error_message=f"Celery dispatch error: {e}")

        for callback in self.callbacks['on_task_queued']:
            try: callback(task)
            except Exception as e: logger.error(f"Error in task queued callback: {e}", exc_info=True)

    def on_task_started(self, task: WorkflowTask):
        task.started_at = datetime.utcnow()
        logger.info(f"Task {task.task_id} started")
        # _save_task_to_redis called by Machine
        for callback in self.callbacks['on_task_started']:
            try: callback(task)
            except Exception as e: logger.error(f"Error in task started callback: {e}")

    def on_task_waiting(self, task: WorkflowTask):
        logger.info(f"Task {task.task_id} waiting for dependencies")
        # _save_task_to_redis called by Machine
        for callback in self.callbacks['on_task_waiting']:
            try: callback(task)
            except Exception as e: logger.error(f"Error in task waiting callback: {e}")

    def on_task_resumed(self, task: WorkflowTask):
        logger.info(f"Task {task.task_id} resumed")
        # _save_task_to_redis called by Machine
        for callback in self.callbacks['on_task_resumed']:
            try: callback(task)
            except Exception as e: logger.error(f"Error in task resumed callback: {e}")

    def on_task_completed(self, task: WorkflowTask):
        task.completed_at = datetime.utcnow()
        logger.info(f"Task {task.task_id} completed")
        # _save_task_to_redis called by Machine
        for callback in self.callbacks['on_task_completed']:
            try: callback(task)
            except Exception as e: logger.error(f"Error in task completed callback: {e}")

    def on_task_failed(self, task: WorkflowTask):
        task.completed_at = datetime.utcnow() # Mark failure time as completion time
        logger.error(f"Task {task.task_id} failed: {task.error_message}")
        # _save_task_to_redis called by Machine
        for callback in self.callbacks['on_task_failed']:
            try: callback(task)
            except Exception as e: logger.error(f"Error in task failed callback: {e}")

    def on_task_retry(self, task: WorkflowTask):
        logger.info(f"Task {task.task_id} retrying (attempt {task.retry_count})")
        # _save_task_to_redis called by Machine
        # Note: retry_count increment should happen before this callback if it's part of the transition logic
        # or be handled within the Celery task itself before re-queueing.
        # The can_retry condition on the transition handles max_retries.
        for callback in self.callbacks['on_task_retry']:
            try: callback(task)
            except Exception as e: logger.error(f"Error in task retry callback: {e}")

    def on_task_cancelled(self, task: WorkflowTask):
        task.completed_at = datetime.utcnow()
        logger.info(f"Task {task.task_id} cancelled")
        # _save_task_to_redis called by Machine
        for callback in self.callbacks['on_task_cancelled']:
            try: callback(task)
            except Exception as e: logger.error(f"Error in task cancelled callback: {e}")

    def on_task_reset(self, task: WorkflowTask):
        task.retry_count = 0
        task.error_message = None
        task.completed_steps.clear()
        task.failed_steps.clear()
        task.step_executions.clear()
        task.final_result = None
        task.conversation_history.clear()
        task.started_at = None
        task.completed_at = None
        logger.info(f"Task {task.task_id} reset")
        # _save_task_to_redis called by Machine
        for callback in self.callbacks['on_task_reset']:
            try: callback(task)
            except Exception as e: logger.error(f"Error in task reset callback: {e}")

# 全域狀態機實例
workflow_state_machine_instance = WorkflowStateMachine()

def get_workflow_state_machine() -> WorkflowStateMachine:
    """取得全域工作流程狀態機實例"""
    return workflow_state_machine_instance
