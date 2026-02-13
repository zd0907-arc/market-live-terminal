from fastapi import APIRouter
from backend.app.models.schemas import APIResponse, AppConfig, ConfigUpdate
from backend.app.db.crud import get_app_config, update_app_config

router = APIRouter()

@router.get("/config", response_model=dict)
def get_config():
    return get_app_config()

@router.get("/config/public", response_model=APIResponse)
def get_public_config():
    """
    前端获取公共配置（阈值等），确保前后端计算口径一致
    """
    config = get_app_config()
    return APIResponse(
        code=200,
        data={
            "large_threshold": float(config.get('large_threshold', 200000)),
            "super_large_threshold": float(config.get('super_large_threshold', 1000000))
        }
    )

from pydantic import BaseModel

@router.post("/config", response_model=APIResponse)
def update_config(config: ConfigUpdate):
    # Support both single key update (legacy) and bulk update logic if needed
    # But schema defines key/value
    update_app_config(config.key, config.value)
    
    # Reload sentiment analyzer keywords if relevant
    if config.key in ['sentiment_bull_words', 'sentiment_bear_words']:
        from backend.app.services.sentiment_analyzer import sentiment_analyzer
        sentiment_analyzer.reload_keywords()
        
    return APIResponse(code=200, message="Config updated")

class LLMConfig(BaseModel):
    base_url: str
    api_key: str
    model: str
    proxy: str = ""

@router.post("/config/test-llm", response_model=APIResponse)
def test_llm_connection(config: LLMConfig):
    from backend.app.services.llm_service import llm_service
    try:
        # 使用传入的配置进行测试，而不是已保存的配置
        llm_service.test_connection(config.dict())
        return APIResponse(code=200, message="连接测试成功")
    except Exception as e:
        return APIResponse(code=500, message=f"连接失败: {str(e)}")
