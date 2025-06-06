"""
Monitoring and Metrics Collection for Multi-Agent System
多智能體系統監控與指標收集模組
"""

import logging
import time
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, generate_latest
from workflow_state_machine import TaskState, WorkflowTask


logger = logging.getLogger(__name__)


@dataclass
class SystemMetrics:
    """系統指標數據類別"""
    total_tasks: int = 0
    active_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    avg_execution_time: float = 0.0
    success_rate: float = 0.0
    celery_workers_active: int = 0
    redis_connections: int = 0
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)


class PrometheusMetricsCollector:
    """Prometheus 指標收集器"""
    
    def __init__(self):
        """初始化 Prometheus 指標"""
        self.registry = CollectorRegistry()
        
        # 任務相關指標
        self.task_counter = Counter(
            'multiagent_tasks_total',
            'Total number of multi-agent tasks',
            ['workflow_name', 'status'],
            registry=self.registry
        )
        
        self.task_duration = Histogram(
            'multiagent_task_duration_seconds',
            'Duration of multi-agent tasks in seconds',
            ['workflow_name', 'agent_name'],
            registry=self.registry
        )
        
        self.active_tasks_gauge = Gauge(
            'multiagent_active_tasks',
            'Number of currently active tasks',
            registry=self.registry
        )
        
        self.workflow_step_counter = Counter(
            'multiagent_workflow_steps_total',
            'Total number of workflow steps executed',
            ['workflow_name', 'step_name', 'agent_name', 'status'],
            registry=self.registry
        )
        
        # 智能體相關指標
        self.agent_execution_counter = Counter(
            'multiagent_agent_executions_total',
            'Total number of agent executions',
            ['agent_name', 'status'],
            registry=self.registry
        )
        
        self.agent_error_counter = Counter(
            'multiagent_agent_errors_total',
            'Total number of agent errors',
            ['agent_name', 'error_type'],
            registry=self.registry
        )
        
        # Celery 相關指標
        self.celery_task_counter = Counter(
            'celery_tasks_total',
            'Total number of Celery tasks',
            ['task_name', 'status'],
            registry=self.registry
        )
        
        self.celery_worker_gauge = Gauge(
            'celery_workers_active',
            'Number of active Celery workers',
            registry=self.registry
        )
        
        # 系統資源指標
        self.memory_usage_gauge = Gauge(
            'system_memory_usage_bytes',
            'System memory usage in bytes',
            registry=self.registry
        )
        
        self.cpu_usage_gauge = Gauge(
            'system_cpu_usage_percent',
            'System CPU usage percentage',
            registry=self.registry
        )
        
        # Redis 連接指標
        self.redis_connections_gauge = Gauge(
            'redis_connections_active',
            'Number of active Redis connections',
            registry=self.registry
        )

    def record_task_start(self, workflow_name: str):
        """記錄任務開始"""
        self.task_counter.labels(workflow_name=workflow_name, status='started').inc()
        self.active_tasks_gauge.inc()

    def record_task_completion(self, workflow_name: str, duration: float, success: bool):
        """記錄任務完成"""
        status = 'completed' if success else 'failed'
        self.task_counter.labels(workflow_name=workflow_name, status=status).inc()
        self.active_tasks_gauge.dec()

    def record_workflow_step(self, workflow_name: str, step_name: str, 
                           agent_name: str, duration: float, success: bool):
        """記錄工作流程步驟"""
        status = 'completed' if success else 'failed'
        self.workflow_step_counter.labels(
            workflow_name=workflow_name,
            step_name=step_name,
            agent_name=agent_name,
            status=status
        ).inc()
        
        self.task_duration.labels(
            workflow_name=workflow_name,
            agent_name=agent_name
        ).observe(duration)

    def record_agent_execution(self, agent_name: str, success: bool, error_type: str = None):
        """記錄智能體執行"""
        status = 'success' if success else 'error'
        self.agent_execution_counter.labels(agent_name=agent_name, status=status).inc()
        
        if not success and error_type:
            self.agent_error_counter.labels(agent_name=agent_name, error_type=error_type).inc()

    def record_celery_task(self, task_name: str, status: str):
        """記錄 Celery 任務"""
        self.celery_task_counter.labels(task_name=task_name, status=status).inc()

    def update_system_metrics(self, metrics: SystemMetrics):
        """更新系統指標"""
        self.celery_worker_gauge.set(metrics.celery_workers_active)
        self.memory_usage_gauge.set(metrics.memory_usage_mb * 1024 * 1024)  # 轉換為 bytes
        self.cpu_usage_gauge.set(metrics.cpu_usage_percent)
        self.redis_connections_gauge.set(metrics.redis_connections)

    def get_metrics(self) -> str:
        """取得 Prometheus 格式的指標"""
        return generate_latest(self.registry)


class TaskPerformanceTracker:
    """任務性能追蹤器"""
    
    def __init__(self):
        """初始化性能追蹤器"""
        self.task_times: Dict[str, Dict[str, float]] = {}
        self.step_times: Dict[str, Dict[str, float]] = {}
        self.performance_history: Dict[str, list] = {}

    def start_tracking(self, task_id: str, step_name: str = None):
        """開始追蹤任務或步驟"""
        current_time = time.time()
        
        if step_name:
            if task_id not in self.step_times:
                self.step_times[task_id] = {}
            self.step_times[task_id][step_name] = current_time
        else:
            self.task_times[task_id] = {'start': current_time}

    def end_tracking(self, task_id: str, step_name: str = None) -> float:
        """結束追蹤並回傳執行時間"""
        current_time = time.time()
        
        if step_name:
            if task_id in self.step_times and step_name in self.step_times[task_id]:
                start_time = self.step_times[task_id][step_name]
                duration = current_time - start_time
                del self.step_times[task_id][step_name]
                return duration
        else:
            if task_id in self.task_times and 'start' in self.task_times[task_id]:
                start_time = self.task_times[task_id]['start']
                duration = current_time - start_time
                self.task_times[task_id]['duration'] = duration
                return duration
        
        return 0.0

    def get_average_performance(self, workflow_name: str) -> Dict[str, float]:
        """取得工作流程的平均性能"""
        if workflow_name not in self.performance_history:
            return {'avg_duration': 0.0, 'task_count': 0}
        
        durations = self.performance_history[workflow_name]
        avg_duration = sum(durations) / len(durations) if durations else 0.0
        
        return {
            'avg_duration': avg_duration,
            'task_count': len(durations),
            'min_duration': min(durations) if durations else 0.0,
            'max_duration': max(durations) if durations else 0.0
        }

    def record_performance(self, workflow_name: str, duration: float):
        """記錄工作流程性能"""
        if workflow_name not in self.performance_history:
            self.performance_history[workflow_name] = []
        
        self.performance_history[workflow_name].append(duration)
        
        # 限制歷史記錄數量，避免記憶體過度使用
        if len(self.performance_history[workflow_name]) > 1000:
            self.performance_history[workflow_name] = self.performance_history[workflow_name][-1000:]


class HealthChecker:
    """系統健康檢查器"""
    
    def __init__(self):
        """初始化健康檢查器"""
        self.last_check_time: Optional[datetime] = None
        self.health_status: Dict[str, Any] = {}

    def check_system_health(self) -> Dict[str, Any]:
        """檢查系統整體健康狀況"""
        current_time = datetime.utcnow()
        
        health_status = {
            'timestamp': current_time.isoformat(),
            'overall_status': 'healthy',
            'components': {},
            'checks_performed': []
        }
        
        # 檢查各個組件
        components_to_check = [
            ('redis', self._check_redis_health),
            ('celery_workers', self._check_celery_workers),
            ('workflow_state_machine', self._check_workflow_state_machine),
            ('config_manager', self._check_config_manager)
        ]
        
        failed_components = 0
        
        for component_name, check_function in components_to_check:
            try:
                component_status = check_function()
                health_status['components'][component_name] = component_status
                health_status['checks_performed'].append(component_name)
                
                if not component_status.get('healthy', False):
                    failed_components += 1
                    
            except Exception as e:
                logger.error(f"Health check failed for {component_name}: {e}")
                health_status['components'][component_name] = {
                    'healthy': False,
                    'error': str(e),
                    'timestamp': current_time.isoformat()
                }
                failed_components += 1
        
        # 決定整體健康狀況
        total_components = len(components_to_check)
        if failed_components == 0:
            health_status['overall_status'] = 'healthy'
        elif failed_components < total_components / 2:
            health_status['overall_status'] = 'degraded'
        else:
            health_status['overall_status'] = 'unhealthy'
        
        health_status['failed_components'] = failed_components
        health_status['total_components'] = total_components
        
        self.last_check_time = current_time
        self.health_status = health_status
        
        return health_status

    def _check_redis_health(self) -> Dict[str, Any]:
        """檢查 Redis 健康狀況"""
        try:
            import redis
            from config_manager import get_config_manager
            
            config_manager = get_config_manager()
            celery_config = config_manager.get_celery_config()
            
            # 解析 Redis URL
            redis_url = celery_config.broker_url
            r = redis.from_url(redis_url)
            
            # 嘗試 ping Redis
            result = r.ping()
            
            # 取得 Redis 資訊
            info = r.info()
            
            return {
                'healthy': result,
                'connected_clients': info.get('connected_clients', 0),
                'used_memory': info.get('used_memory', 0),
                'redis_version': info.get('redis_version', 'unknown'),
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'healthy': False,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }

    def _check_celery_workers(self) -> Dict[str, Any]:
        """檢查 Celery Workers 健康狀況"""
        try:
            from agent_tasks import app
            
            # 檢查活躍的 workers
            inspect = app.control.inspect()
            active_workers = inspect.active()
            stats = inspect.stats()
            
            worker_count = len(active_workers) if active_workers else 0
            
            return {
                'healthy': worker_count > 0,
                'active_workers': worker_count,
                'worker_stats': stats,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'healthy': False,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }

    def _check_workflow_state_machine(self) -> Dict[str, Any]:
        """檢查工作流程狀態機健康狀況"""
        try:
            from workflow_state_machine import get_workflow_state_machine
            
            state_machine = get_workflow_state_machine()
            stats = state_machine.get_task_statistics()
            
            return {
                'healthy': True,
                'task_statistics': stats,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'healthy': False,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }

    def _check_config_manager(self) -> Dict[str, Any]:
        """檢查配置管理器健康狀況"""
        try:
            from config_manager import get_config_manager
            
            config_manager = get_config_manager()
            validation_result = config_manager.validate_configuration()
            
            return {
                'healthy': validation_result['valid'],
                'validation_result': validation_result,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'healthy': False,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }

    def get_health_summary(self) -> Dict[str, Any]:
        """取得健康狀況摘要"""
        if not self.health_status:
            return self.check_system_health()
        
        return {
            'overall_status': self.health_status.get('overall_status', 'unknown'),
            'last_check': self.last_check_time.isoformat() if self.last_check_time else None,
            'components_healthy': len([c for c in self.health_status.get('components', {}).values() 
                                     if c.get('healthy', False)]),
            'total_components': self.health_status.get('total_components', 0)
        }


# 全域監控實例
prometheus_collector = PrometheusMetricsCollector()
performance_tracker = TaskPerformanceTracker()
health_checker = HealthChecker()


def get_prometheus_collector() -> PrometheusMetricsCollector:
    """取得 Prometheus 指標收集器"""
    return prometheus_collector


def get_performance_tracker() -> TaskPerformanceTracker:
    """取得任務性能追蹤器"""
    return performance_tracker


def get_health_checker() -> HealthChecker:
    """取得健康檢查器"""
    return health_checker


def log_task_event(event_type: str, task_id: str, **kwargs):
    """記錄任務事件到日誌"""
    logger.info(
        f"Task event: {event_type}",
        extra={
            'event_type': event_type,
            'task_id': task_id,
            'timestamp': datetime.utcnow().isoformat(),
            **kwargs
        }
    )


def log_agent_event(event_type: str, agent_name: str, **kwargs):
    """記錄智能體事件到日誌"""
    logger.info(
        f"Agent event: {event_type}",
        extra={
            'event_type': event_type,
            'agent_name': agent_name,
            'timestamp': datetime.utcnow().isoformat(),
            **kwargs
        }
    )


def log_workflow_event(event_type: str, workflow_name: str, **kwargs):
    """記錄工作流程事件到日誌"""
    logger.info(
        f"Workflow event: {event_type}",
        extra={
            'event_type': event_type,
            'workflow_name': workflow_name,
            'timestamp': datetime.utcnow().isoformat(),
            **kwargs
        }
    )
