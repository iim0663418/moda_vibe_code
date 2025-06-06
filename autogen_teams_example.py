"""
AutoGen Teams Example - 基於官方文檔範例
使用 RoundRobinGroupChat 實現多代理團隊協作
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.base import TaskResult
from autogen_agentchat.conditions import TextMentionTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_core import CancellationToken
from autogen_ext.models.openai import AzureOpenAIChatCompletionClient

from config import get_settings

logger = logging.getLogger(__name__)


class AutoGenTeamsManager:
    """AutoGen Teams 管理器 - 基於官方範例實現"""
    
    def __init__(self):
        self.settings = get_settings()
        self.model_client = None
        self.teams = {}
        
    async def initialize(self):
        """初始化 Azure OpenAI 客戶端"""
        max_retries = 3
        retry_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                logger.info(f"正在初始化 Azure OpenAI 客戶端 (嘗試 {attempt + 1}/{max_retries})")
                
                # 驗證必要設定
                self._validate_settings()
                
                # 使用 AzureOpenAIChatCompletionClient（正確的 Azure OpenAI 客戶端）
                self.model_client = AzureOpenAIChatCompletionClient(
                    model=self.settings.azure_openai_deployment_name,
                    api_key=self.settings.azure_openai_api_key,
                    azure_endpoint=self.settings.azure_openai_endpoint,
                    api_version=self.settings.azure_openai_api_version,
                    azure_deployment=self.settings.azure_openai_deployment_name,
                )
                
                # 執行連接測試
                await self._test_connection()
                
                logger.info("Azure OpenAI 客戶端初始化成功")
                return
                
            except Exception as e:
                logger.error(f"Azure OpenAI 客戶端初始化失敗 (嘗試 {attempt + 1}/{max_retries}): {e}")
                
                if attempt == max_retries - 1:
                    logger.error("所有重試嘗試已用盡，初始化失敗")
                    raise
                
                logger.info(f"等待 {retry_delay} 秒後重試...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # 指數退避
    
    def _validate_settings(self):
        """驗證必要的設定參數"""
        required_settings = {
            'azure_openai_api_key': self.settings.azure_openai_api_key,
            'azure_openai_endpoint': self.settings.azure_openai_endpoint,
            'azure_openai_deployment_name': self.settings.azure_openai_deployment_name,
            'azure_openai_api_version': self.settings.azure_openai_api_version,
        }
        
        missing_settings = [name for name, value in required_settings.items() if not value]
        
        if missing_settings:
            raise ValueError(f"缺少必要的設定參數: {', '.join(missing_settings)}")
        
        logger.debug(f"設定驗證通過: endpoint={self.settings.azure_openai_endpoint}, "
                    f"deployment={self.settings.azure_openai_deployment_name}, "
                    f"api_version={self.settings.azure_openai_api_version}")
    
    async def _test_connection(self):
        """測試 Azure OpenAI 連接"""
        try:
            logger.debug("正在測試 Azure OpenAI 連接...")
            
            # 創建簡單的測試訊息 - 使用 AzureOpenAIChatCompletionClient 支援的訊息類型
            from autogen_core.models import UserMessage
            test_messages = [UserMessage(content="Hello", source="test")]
            
            # 測試 token 計數功能（這不會消耗 API 配額）
            token_count = self.model_client.count_tokens(test_messages)
            logger.debug(f"連接測試成功，測試訊息 token 數量: {token_count}")
            
        except Exception as e:
            logger.error(f"Azure OpenAI 連接測試失敗: {e}")
            raise ConnectionError(f"無法連接到 Azure OpenAI 服務: {e}")
    
    def create_reflection_team(self) -> RoundRobinGroupChat:
        """
        創建反思團隊 - 基於官方文檔的 reflection pattern
        包含主要代理和評論代理
        """
        # 創建主要代理
        primary_agent = AssistantAgent(
            "primary",
            model_client=self.model_client,
            system_message="You are a helpful AI assistant. Provide comprehensive and accurate responses to user queries.",
        )
        
        # 創建評論代理
        critic_agent = AssistantAgent(
            "critic",
            model_client=self.model_client,
            system_message="Provide constructive feedback on the primary agent's response. Respond with 'APPROVE' when your feedback is addressed satisfactorily.",
        )
        
        # 定義終止條件
        text_termination = TextMentionTermination("APPROVE")
        
        # 創建團隊
        team = RoundRobinGroupChat(
            [primary_agent, critic_agent], 
            termination_condition=text_termination
        )
        
        self.teams["reflection"] = team
        return team
    
    def create_research_team(self) -> RoundRobinGroupChat:
        """
        創建研究團隊 - 多角色協作
        """
        # 研究員代理
        researcher_agent = AssistantAgent(
            "researcher",
            model_client=self.model_client,
            system_message="""You are a research specialist. Your role is to:
1. Gather and analyze information on given topics
2. Provide factual, well-sourced research findings
3. Identify key insights and patterns
When your research is complete, say 'RESEARCH_COMPLETE'.""",
        )
        
        # 分析師代理
        analyst_agent = AssistantAgent(
            "analyst",
            model_client=self.model_client,
            system_message="""You are a data analyst. Your role is to:
1. Analyze research findings provided by the researcher
2. Identify trends, patterns, and correlations
3. Provide analytical insights and recommendations
When your analysis is complete, say 'ANALYSIS_COMPLETE'.""",
        )
        
        # 報告員代理
        reporter_agent = AssistantAgent(
            "reporter",
            model_client=self.model_client,
            system_message="""You are a report writer. Your role is to:
1. Synthesize research and analysis into clear reports
2. Structure information in a logical, readable format
3. Provide actionable conclusions and recommendations
When your report is complete, say 'REPORT_COMPLETE'.""",
        )
        
        # 定義終止條件
        text_termination = TextMentionTermination("REPORT_COMPLETE")
        
        # 創建團隊
        team = RoundRobinGroupChat(
            [researcher_agent, analyst_agent, reporter_agent],
            termination_condition=text_termination
        )
        
        self.teams["research"] = team
        return team
    
    def create_creative_team(self) -> RoundRobinGroupChat:
        """
        創建創意團隊 - 創意寫作協作
        """
        # 創意代理
        creative_agent = AssistantAgent(
            "creative_writer",
            model_client=self.model_client,
            system_message="""You are a creative writer. Your role is to:
1. Generate original, engaging content
2. Use vivid imagery and compelling narratives
3. Create content that resonates with the target audience
Focus on creativity and originality.""",
        )
        
        # 編輯代理
        editor_agent = AssistantAgent(
            "editor",
            model_client=self.model_client,
            system_message="""You are an experienced editor. Your role is to:
1. Review and improve written content
2. Ensure clarity, coherence, and flow
3. Provide specific suggestions for improvement
4. When satisfied with the content, respond with 'APPROVED_FOR_PUBLICATION'.""",
        )
        
        # 定義終止條件
        text_termination = TextMentionTermination("APPROVED_FOR_PUBLICATION")
        
        # 創建團隊
        team = RoundRobinGroupChat(
            [creative_agent, editor_agent],
            termination_condition=text_termination
        )
        
        self.teams["creative"] = team
        return team
    
    async def run_team_task(
        self, 
        team_name: str, 
        task: str, 
        stream: bool = False,
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        執行團隊任務
        
        Args:
            team_name: 團隊名稱 ('reflection', 'research', 'creative')
            task: 任務描述
            stream: 是否使用串流模式
            timeout: 任務超時時間（秒），None 表示無超時限制
            
        Returns:
            包含結果和元數據的字典
        """
        if team_name not in self.teams:
            available_teams = list(self.teams.keys())
            raise ValueError(f"未知的團隊名稱: {team_name}. 可用團隊: {available_teams}")
        
        # 驗證輸入
        if not task or not task.strip():
            raise ValueError("任務描述不能為空")
        
        if len(task) > 10000:  # 限制任務長度
            raise ValueError("任務描述過長，請限制在 10000 字符以內")
        
        team = self.teams[team_name]
        start_time = datetime.utcnow()
        task_id = f"{team_name}_{start_time.strftime('%Y%m%d_%H%M%S')}"
        
        logger.info(f"開始執行團隊任務 [ID: {task_id}] - 團隊: {team_name}, 串流模式: {stream}")
        logger.debug(f"任務內容 [ID: {task_id}]: {task[:200]}...")
        
        try:
            # 設置超時
            timeout_value = timeout or 300.0  # 默認 5 分鐘超時
            
            if stream:
                # 使用串流模式
                messages = []
                message_count = 0
                
                async def run_with_stream():
                    nonlocal message_count
                    async for message in team.run_stream(task=task):
                        if isinstance(message, TaskResult):
                            return message
                        else:
                            message_count += 1
                            message_data = {
                                "source": message.source,
                                "content": message.content,
                                "type": message.type,
                                "timestamp": datetime.utcnow().isoformat(),
                                "sequence": message_count
                            }
                            messages.append(message_data)
                            
                            # 記錄訊息（截斷長內容）
                            content_preview = message.content[:100] + "..." if len(message.content) > 100 else message.content
                            logger.info(f"[{task_id}][{message.source}]: {content_preview}")
                    
                    raise RuntimeError("串流意外結束，未收到 TaskResult")
                
                result = await asyncio.wait_for(run_with_stream(), timeout=timeout_value)
                
            else:
                # 標準模式
                logger.debug(f"使用標準模式執行任務 [ID: {task_id}]")
                result = await asyncio.wait_for(team.run(task=task), timeout=timeout_value)
                
                messages = []
                for i, msg in enumerate(result.messages, 1):
                    message_data = {
                        "source": msg.source,
                        "content": msg.content,
                        "type": msg.type,
                        "models_usage": msg.models_usage.__dict__ if msg.models_usage else None,
                        "timestamp": datetime.utcnow().isoformat(),
                        "sequence": i
                    }
                    messages.append(message_data)
            
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            
            # 計算統計資訊
            total_tokens = 0
            total_cost = 0.0
            for msg in messages:
                if msg.get("models_usage"):
                    usage = msg["models_usage"]
                    if isinstance(usage, dict):
                        total_tokens += usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
            
            logger.info(f"任務執行完成 [ID: {task_id}] - 耗時: {duration:.2f}秒, "
                       f"訊息數: {len(messages)}, 停止原因: {result.stop_reason}")
            
            return {
                "success": True,
                "task_id": task_id,
                "team_name": team_name,
                "task": task,
                "result": {
                    "stop_reason": result.stop_reason,
                    "message_count": len(result.messages),
                    "messages": messages
                },
                "metadata": {
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                    "duration_seconds": duration,
                    "stream_mode": stream,
                    "timeout_used": timeout_value,
                    "total_tokens": total_tokens,
                    "performance": {
                        "messages_per_second": len(messages) / duration if duration > 0 else 0,
                        "avg_message_length": sum(len(msg["content"]) for msg in messages) / len(messages) if messages else 0
                    }
                }
            }
            
        except asyncio.TimeoutError:
            duration = (datetime.utcnow() - start_time).total_seconds()
            error_msg = f"任務執行超時 ({timeout_value}秒)"
            logger.error(f"[{task_id}] {error_msg}")
            
            return {
                "success": False,
                "task_id": task_id,
                "team_name": team_name,
                "task": task,
                "error": error_msg,
                "error_type": "timeout",
                "metadata": {
                    "start_time": start_time.isoformat(),
                    "duration_seconds": duration,
                    "timeout_limit": timeout_value,
                    "stream_mode": stream
                }
            }
            
        except ValueError as e:
            duration = (datetime.utcnow() - start_time).total_seconds()
            error_msg = f"輸入驗證錯誤: {str(e)}"
            logger.error(f"[{task_id}] {error_msg}")
            
            return {
                "success": False,
                "task_id": task_id,
                "team_name": team_name,
                "task": task,
                "error": error_msg,
                "error_type": "validation",
                "metadata": {
                    "start_time": start_time.isoformat(),
                    "duration_seconds": duration
                }
            }
            
        except ConnectionError as e:
            duration = (datetime.utcnow() - start_time).total_seconds()
            error_msg = f"連接錯誤: {str(e)}"
            logger.error(f"[{task_id}] {error_msg}")
            
            return {
                "success": False,
                "task_id": task_id,
                "team_name": team_name,
                "task": task,
                "error": error_msg,
                "error_type": "connection",
                "metadata": {
                    "start_time": start_time.isoformat(),
                    "duration_seconds": duration,
                    "retry_suggestion": "請檢查網路連接和 Azure OpenAI 服務狀態"
                }
            }
            
        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds()
            error_msg = f"未預期的錯誤: {str(e)}"
            logger.error(f"[{task_id}] {error_msg}", exc_info=True)
            
            return {
                "success": False,
                "task_id": task_id,
                "team_name": team_name,
                "task": task,
                "error": error_msg,
                "error_type": "unexpected",
                "metadata": {
                    "start_time": start_time.isoformat(),
                    "duration_seconds": duration,
                    "exception_type": type(e).__name__
                }
            }
    
    async def reset_team(self, team_name: str):
        """重置團隊狀態"""
        if team_name in self.teams:
            await self.teams[team_name].reset()
            logger.info(f"團隊 {team_name} 已重置")
    
    async def close(self):
        """關閉客戶端連接"""
        if self.model_client:
            await self.model_client.close()
            logger.info("模型客戶端已關閉")


# 使用範例
async def example_usage():
    """使用範例"""
    # 初始化團隊管理器
    manager = AutoGenTeamsManager()
    await manager.initialize()
    
    try:
        # 創建反思團隊
        reflection_team = manager.create_reflection_team()
        
        # 執行詩歌創作任務（基於官方範例）
        task = "Write a short poem about the fall season."
        result = await manager.run_team_task("reflection", task, stream=False)
        
        print("=== 反思團隊結果 ===")
        print(f"任務: {result['task']}")
        print(f"停止原因: {result['result']['stop_reason']}")
        print(f"訊息數量: {result['result']['message_count']}")
        print(f"執行時間: {result['metadata']['duration_seconds']:.2f} 秒")
        
        # 顯示對話記錄
        for msg in result['result']['messages']:
            print(f"\n[{msg['source']}]: {msg['content']}")
        
        # 創建研究團隊
        research_team = manager.create_research_team()
        
        # 執行研究任務
        research_task = "Research the impact of artificial intelligence on modern education"
        research_result = await manager.run_team_task("research", research_task, stream=True)
        
        print("\n=== 研究團隊結果 ===")
        print(f"任務: {research_result['task']}")
        print(f"成功: {research_result['success']}")
        
    finally:
        await manager.close()


if __name__ == "__main__":
    # 運行範例
    asyncio.run(example_usage())
