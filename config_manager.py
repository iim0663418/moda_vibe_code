"""
Configuration Manager for Multi-Agent System
管理智能體協作規則配置檔的讀取與驗證
"""

import yaml
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from pydantic import BaseModel, Field, validator
from enum import Enum


logger = logging.getLogger(__name__)


class TaskAssignmentStrategy(str, Enum):
    """任務分配策略"""
    PRIORITY_BASED = "priority_based"
    ROUND_ROBIN = "round_robin"
    LOAD_BALANCED = "load_balanced"


class MessageFormat(str, Enum):
    """訊息格式"""
    STRUCTURED = "structured"
    PLAIN = "plain"


class FallbackStrategy(str, Enum):
    """錯誤回補策略"""
    SINGLE_AGENT_SIMULATION = "single_agent_simulation"
    RETRY = "retry"
    SKIP = "skip"


class AgentConfig(BaseModel):
    """智能體配置模型"""
    name: str
    role: str
    description: str
    capabilities: List[str]
    max_retries: int = Field(default=3, ge=0, le=10)
    timeout_seconds: int = Field(default=30, ge=5, le=600)
    priority: int = Field(default=1, ge=1, le=10)


class WorkflowStep(BaseModel):
    """工作流程步驟模型"""
    name: str
    agent: str
    required: bool = True
    dependencies: List[str] = Field(default_factory=list)
    retry_on_failure: bool = True


class Workflow(BaseModel):
    """工作流程模型"""
    name: str
    description: str
    steps: List[WorkflowStep]


class TaskAssignmentConfig(BaseModel):
    """任務分配配置"""
    strategy: TaskAssignmentStrategy = TaskAssignmentStrategy.PRIORITY_BASED
    load_balancing: bool = True
    max_concurrent_tasks: int = Field(default=5, ge=1, le=50)


class CommunicationConfig(BaseModel):
    """通訊配置"""
    message_format: MessageFormat = MessageFormat.STRUCTURED
    include_metadata: bool = True
    timeout_seconds: int = Field(default=120, ge=30, le=600)
    max_message_length: int = Field(default=8192, ge=1024, le=32768)


class ErrorHandlingConfig(BaseModel):
    """錯誤處理配置"""
    auto_retry: bool = True
    max_global_retries: int = Field(default=3, ge=0, le=10)
    fallback_strategy: FallbackStrategy = FallbackStrategy.SINGLE_AGENT_SIMULATION
    escalation_threshold: int = Field(default=2, ge=1, le=5)


class MonitoringConfig(BaseModel):
    """監控配置"""
    track_performance: bool = True
    log_all_interactions: bool = True
    metrics_collection: bool = True
    health_check_interval: int = Field(default=30, ge=10, le=300)


class CollaborationRules(BaseModel):
    """協作規則配置"""
    task_assignment: TaskAssignmentConfig
    communication: CommunicationConfig
    error_handling: ErrorHandlingConfig
    monitoring: MonitoringConfig


class StateTransition(BaseModel):
    """狀態轉換配置"""
    trigger: str
    source: str | List[str]
    dest: str


class StateMachineConfig(BaseModel):
    """狀態機配置"""
    states: List[str]
    transitions: List[StateTransition]


class CeleryWorkerConfig(BaseModel):
    """Celery 工作者配置"""
    concurrency: int = Field(default=4, ge=1, le=16)
    max_tasks_per_child: int = Field(default=1000, ge=100, le=10000)
    task_soft_time_limit: int = Field(default=300, ge=60, le=3600)
    task_time_limit: int = Field(default=600, ge=120, le=7200)


class CeleryConfig(BaseModel):
    """Celery 配置"""
    broker_url: str = "redis://redis:6379/0"
    result_backend: str = "redis://redis:6379/0"
    task_serializer: str = "json"
    accept_content: List[str] = Field(default_factory=lambda: ["json"])
    result_serializer: str = "json"
    timezone: str = "Asia/Taipei"
    enable_utc: bool = True
    task_routes: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    worker_config: CeleryWorkerConfig = Field(default_factory=CeleryWorkerConfig)


class PrometheusConfig(BaseModel):
    """Prometheus 監控配置"""
    enabled: bool = True
    port: int = Field(default=9090, ge=1024, le=65535)
    metrics_path: str = "/metrics"


class HealthCheckConfig(BaseModel):
    """健康檢查配置"""
    enabled: bool = True
    interval_seconds: int = Field(default=30, ge=10, le=300)
    timeout_seconds: int = Field(default=10, ge=1, le=60)


class LoggingMonitoringConfig(BaseModel):
    """日誌監控配置"""
    level: str = "INFO"
    format: str = "json"
    include_task_metadata: bool = True


class MonitoringSystemConfig(BaseModel):
    """監控系統配置"""
    prometheus: PrometheusConfig = Field(default_factory=PrometheusConfig)
    health_checks: HealthCheckConfig = Field(default_factory=HealthCheckConfig)
    logging: LoggingMonitoringConfig = Field(default_factory=LoggingMonitoringConfig)


class AuthenticationConfig(BaseModel):
    """認證配置"""
    required: bool = False
    method: str = "token"


class AuthorizationConfig(BaseModel):
    """授權配置"""
    enabled: bool = False
    role_based: bool = False


class EncryptionConfig(BaseModel):
    """加密配置"""
    in_transit: bool = False
    at_rest: bool = False


class SecurityConfig(BaseModel):
    """安全配置"""
    authentication: AuthenticationConfig = Field(default_factory=AuthenticationConfig)
    authorization: AuthorizationConfig = Field(default_factory=AuthorizationConfig)
    encryption: EncryptionConfig = Field(default_factory=EncryptionConfig)


class MetadataConfig(BaseModel):
    """配置檔元資料"""
    name: str
    description: str
    created: str
    author: str


class AgentCollaborationConfig(BaseModel):
    """智能體協作配置主模型"""
    version: str
    metadata: MetadataConfig
    agents: Dict[str, AgentConfig]
    workflows: Dict[str, Workflow]
    collaboration_rules: CollaborationRules
    state_machine: StateMachineConfig
    celery: CeleryConfig
    monitoring: MonitoringSystemConfig
    security: SecurityConfig

    @validator('agents')
    def validate_agents(cls, v):
        """驗證智能體配置"""
        if not v:
            raise ValueError("At least one agent must be configured")
        
        # 檢查必要的智能體角色
        required_agents = {'fetcher', 'summarizer', 'analyzer', 'coordinator', 'responder'}
        configured_agents = set(v.keys())
        missing_agents = required_agents - configured_agents
        
        if missing_agents:
            logger.warning(f"Missing recommended agents: {missing_agents}")
        
        return v

    @validator('workflows')
    def validate_workflows(cls, v):
        """驗證工作流程配置"""
        if not v:
            raise ValueError("At least one workflow must be configured")
        
        # 檢查是否有預設工作流程
        if 'default' not in v:
            raise ValueError("A 'default' workflow must be configured")
        
        return v


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置檔路徑，預設為 config/agent_collaboration_rules.yaml
        """
        if config_path is None:
            # 預設配置檔路徑
            self.config_path = Path(__file__).parent / "config" / "agent_collaboration_rules.yaml"
        else:
            self.config_path = Path(config_path)
        
        self._config: Optional[AgentCollaborationConfig] = None
        self._loaded = False

    def load_config(self) -> AgentCollaborationConfig:
        """
        載入配置檔
        
        Returns:
            AgentCollaborationConfig: 解析後的配置物件
            
        Raises:
            FileNotFoundError: 配置檔不存在
            ValueError: 配置檔格式錯誤
        """
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            
            # 使用 Pydantic 驗證配置
            self._config = AgentCollaborationConfig(**config_data)
            self._loaded = True
            
            logger.info(f"Configuration loaded successfully from {self.config_path}")
            return self._config
            
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML format in configuration file: {e}")
        except Exception as e:
            raise ValueError(f"Error loading configuration: {e}")

    def get_config(self) -> AgentCollaborationConfig:
        """
        取得配置物件，如果尚未載入則自動載入
        
        Returns:
            AgentCollaborationConfig: 配置物件
        """
        if not self._loaded or self._config is None:
            return self.load_config()
        return self._config

    def reload_config(self) -> AgentCollaborationConfig:
        """
        重新載入配置檔
        
        Returns:
            AgentCollaborationConfig: 重新載入的配置物件
        """
        self._config = None
        self._loaded = False
        return self.load_config()

    def get_agent_config(self, agent_name: str) -> Optional[AgentConfig]:
        """
        取得特定智能體的配置
        
        Args:
            agent_name: 智能體名稱
            
        Returns:
            AgentConfig: 智能體配置，如果不存在則回傳 None
        """
        config = self.get_config()
        return config.agents.get(agent_name)

    def get_workflow_config(self, workflow_name: str = "default") -> Optional[Workflow]:
        """
        取得工作流程配置
        
        Args:
            workflow_name: 工作流程名稱，預設為 "default"
            
        Returns:
            Workflow: 工作流程配置，如果不存在則回傳 None
        """
        config = self.get_config()
        return config.workflows.get(workflow_name)

    def get_collaboration_rules(self) -> CollaborationRules:
        """
        取得協作規則配置
        
        Returns:
            CollaborationRules: 協作規則配置
        """
        config = self.get_config()
        return config.collaboration_rules

    def get_celery_config(self) -> CeleryConfig:
        """
        取得 Celery 配置
        
        Returns:
            CeleryConfig: Celery 配置
        """
        config = self.get_config()
        return config.celery

    def get_state_machine_config(self) -> StateMachineConfig:
        """
        取得狀態機配置
        
        Returns:
            StateMachineConfig: 狀態機配置
        """
        config = self.get_config()
        return config.state_machine

    def validate_configuration(self) -> Dict[str, Any]:
        """
        驗證配置檔的完整性和有效性
        
        Returns:
            Dict: 驗證結果，包含是否有效和錯誤訊息
        """
        try:
            config = self.get_config()
            
            validation_result = {
                "valid": True,
                "warnings": [],
                "errors": []
            }
            
            # 檢查智能體配置的完整性
            configured_agents = set(config.agents.keys())
            required_agents = {'fetcher', 'summarizer', 'analyzer', 'coordinator', 'responder'}
            missing_agents = required_agents - configured_agents
            
            if missing_agents:
                validation_result["warnings"].append(f"Missing recommended agents: {missing_agents}")
            
            # 檢查工作流程是否引用了存在的智能體
            for workflow_name, workflow in config.workflows.items():
                for step in workflow.steps:
                    if step.agent not in configured_agents:
                        validation_result["errors"].append(
                            f"Workflow '{workflow_name}' references unknown agent '{step.agent}'"
                        )
                        validation_result["valid"] = False
            
            # 檢查工作流程的依賴關係
            for workflow_name, workflow in config.workflows.items():
                step_names = {step.name for step in workflow.steps}
                for step in workflow.steps:
                    invalid_deps = set(step.dependencies) - step_names
                    if invalid_deps:
                        validation_result["errors"].append(
                            f"Workflow '{workflow_name}' step '{step.name}' has invalid dependencies: {invalid_deps}"
                        )
                        validation_result["valid"] = False
            
            return validation_result
            
        except Exception as e:
            return {
                "valid": False,
                "warnings": [],
                "errors": [f"Configuration validation failed: {e}"]
            }

    def export_config_dict(self) -> Dict[str, Any]:
        """
        將配置匯出為字典格式
        
        Returns:
            Dict: 配置字典
        """
        config = self.get_config()
        return config.dict()


# 全域配置管理器實例
config_manager = ConfigManager()


def get_config_manager() -> ConfigManager:
    """
    取得全域配置管理器實例
    
    Returns:
        ConfigManager: 配置管理器實例
    """
    return config_manager
