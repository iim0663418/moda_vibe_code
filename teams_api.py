"""
AutoGen Teams API - FastAPI 端點
提供 Teams 功能的 RESTful API
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
import logging
from datetime import datetime

from autogen_teams_example import AutoGenTeamsManager

logger = logging.getLogger(__name__)

# 創建路由器
router = APIRouter(prefix="/teams", tags=["AutoGen Teams"])

# 全局團隊管理器實例
teams_manager: Optional[AutoGenTeamsManager] = None


# Pydantic 模型
class TeamTaskRequest(BaseModel):
    """團隊任務請求模型"""
    team_name: str = Field(..., description="團隊名稱", example="reflection")
    task: str = Field(..., description="任務描述", example="Write a short poem about the fall season.")
    stream: bool = Field(default=False, description="是否使用串流模式")
    timeout: Optional[float] = Field(default=None, description="任務超時時間（秒），None 表示使用預設值")


class TeamTaskResponse(BaseModel):
    """團隊任務回應模型"""
    success: bool
    team_name: str
    task: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Dict[str, Any]


class TeamListResponse(BaseModel):
    """團隊列表回應模型"""
    available_teams: List[str]
    description: Dict[str, str]


class TeamStatusResponse(BaseModel):
    """團隊狀態回應模型"""
    manager_initialized: bool
    available_teams: List[str]
    teams_created: List[str]


# 初始化函數（由 main.py 調用）
async def initialize_teams_manager():
    """初始化團隊管理器"""
    global teams_manager
    try:
        teams_manager = AutoGenTeamsManager()
        await teams_manager.initialize()
        logger.info("AutoGen Teams 管理器初始化成功")
    except Exception as e:
        logger.error(f"AutoGen Teams 管理器初始化失敗: {e}")
        teams_manager = None


async def shutdown_teams_manager():
    """關閉團隊管理器"""
    global teams_manager
    if teams_manager:
        try:
            await teams_manager.close()
            logger.info("AutoGen Teams 管理器已關閉")
        except Exception as e:
            logger.error(f"關閉 AutoGen Teams 管理器時出錯: {e}")


@router.get("/status", response_model=TeamStatusResponse)
async def get_teams_status():
    """獲取團隊系統狀態"""
    global teams_manager
    
    if not teams_manager:
        return TeamStatusResponse(
            manager_initialized=False,
            available_teams=[],
            teams_created=[]
        )
    
    return TeamStatusResponse(
        manager_initialized=True,
        available_teams=["reflection", "research", "creative"],
        teams_created=list(teams_manager.teams.keys())
    )


@router.get("/list", response_model=TeamListResponse)
async def list_available_teams():
    """列出可用的團隊類型"""
    return TeamListResponse(
        available_teams=["reflection", "research", "creative"],
        description={
            "reflection": "反思團隊 - 主要代理和評論代理協作，適用於需要反覆改進的任務",
            "research": "研究團隊 - 研究員、分析師、報告員協作，適用於研究分析任務",
            "creative": "創意團隊 - 創意寫手和編輯協作，適用於創意寫作任務"
        }
    )


@router.post("/create/{team_name}")
async def create_team(team_name: str):
    """創建指定類型的團隊"""
    global teams_manager
    
    if not teams_manager:
        raise HTTPException(status_code=500, detail="Teams 管理器未初始化")
    
    try:
        if team_name == "reflection":
            team = teams_manager.create_reflection_team()
        elif team_name == "research":
            team = teams_manager.create_research_team()
        elif team_name == "creative":
            team = teams_manager.create_creative_team()
        else:
            raise HTTPException(
                status_code=400, 
                detail=f"未知的團隊類型: {team_name}. 可用類型: reflection, research, creative"
            )
        
        return {
            "success": True,
            "message": f"團隊 '{team_name}' 創建成功",
            "team_name": team_name,
            "participants": len(team.participants)
        }
        
    except Exception as e:
        logger.error(f"創建團隊 {team_name} 失敗: {e}")
        raise HTTPException(status_code=500, detail=f"創建團隊失敗: {str(e)}")


@router.post("/run", response_model=TeamTaskResponse)
async def run_team_task(request: TeamTaskRequest):
    """執行團隊任務"""
    global teams_manager
    
    if not teams_manager:
        raise HTTPException(status_code=500, detail="Teams 管理器未初始化")
    
    # 如果團隊不存在，先創建
    if request.team_name not in teams_manager.teams:
        try:
            if request.team_name == "reflection":
                teams_manager.create_reflection_team()
            elif request.team_name == "research":
                teams_manager.create_research_team()
            elif request.team_name == "creative":
                teams_manager.create_creative_team()
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"未知的團隊類型: {request.team_name}"
                )
        except Exception as e:
            logger.error(f"自動創建團隊 {request.team_name} 失敗: {e}")
            raise HTTPException(status_code=500, detail=f"創建團隊失敗: {str(e)}")
    
    try:
        result = await teams_manager.run_team_task(
            team_name=request.team_name,
            task=request.task,
            stream=request.stream,
            timeout=request.timeout
        )
        
        return TeamTaskResponse(**result)
        
    except ValueError as e:
        logger.error(f"輸入驗證錯誤: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except ConnectionError as e:
        logger.error(f"連接錯誤: {e}")
        raise HTTPException(status_code=503, detail=f"服務暫時不可用: {str(e)}")
    except Exception as e:
        logger.error(f"執行團隊任務失敗: {e}")
        raise HTTPException(status_code=500, detail=f"執行任務失敗: {str(e)}")


@router.post("/reset/{team_name}")
async def reset_team(team_name: str):
    """重置指定團隊的狀態"""
    global teams_manager
    
    if not teams_manager:
        raise HTTPException(status_code=500, detail="Teams 管理器未初始化")
    
    if team_name not in teams_manager.teams:
        raise HTTPException(status_code=404, detail=f"團隊 '{team_name}' 不存在")
    
    try:
        await teams_manager.reset_team(team_name)
        return {
            "success": True,
            "message": f"團隊 '{team_name}' 已重置",
            "team_name": team_name
        }
    except Exception as e:
        logger.error(f"重置團隊 {team_name} 失敗: {e}")
        raise HTTPException(status_code=500, detail=f"重置團隊失敗: {str(e)}")


@router.get("/teams/{team_name}/info")
async def get_team_info(team_name: str):
    """獲取指定團隊的詳細資訊"""
    global teams_manager
    
    if not teams_manager:
        raise HTTPException(status_code=500, detail="Teams 管理器未初始化")
    
    if team_name not in teams_manager.teams:
        raise HTTPException(status_code=404, detail=f"團隊 '{team_name}' 不存在")
    
    team = teams_manager.teams[team_name]
    
    return {
        "team_name": team_name,
        "participants": [
            {
                "name": agent.name,
                "type": type(agent).__name__
            }
            for agent in team.participants
        ],
        "participant_count": len(team.participants),
        "termination_condition": type(team.termination_condition).__name__
    }


# 範例用途的測試端點
@router.post("/test/reflection")
async def test_reflection_team():
    """測試反思團隊 - 詩歌創作範例"""
    request = TeamTaskRequest(
        team_name="reflection",
        task="Write a short poem about the fall season.",
        stream=False
    )
    return await run_team_task(request)


@router.post("/test/research")
async def test_research_team():
    """測試研究團隊 - 研究分析範例"""
    request = TeamTaskRequest(
        team_name="research",
        task="Research the impact of artificial intelligence on modern education",
        stream=False
    )
    return await run_team_task(request)


@router.post("/test/creative")
async def test_creative_team():
    """測試創意團隊 - 創意寫作範例"""
    request = TeamTaskRequest(
        team_name="creative",
        task="Write a compelling product description for a new eco-friendly smartphone",
        stream=False
    )
    return await run_team_task(request)
