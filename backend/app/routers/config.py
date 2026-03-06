import os
from fastapi import APIRouter
from backend.app.models.schemas import APIResponse, ConfigUpdate
from backend.app.db.crud import get_app_config, update_app_config

router = APIRouter()

@router.get("/config", response_model=dict)
def get_config():
    """返回业务配置（阈值、情绪关键词等），不包含任何 LLM 敏感信息"""
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

@router.get("/config/llm-info", response_model=APIResponse)
def get_llm_info():
    """
    返回 LLM 的脱敏信息（仅模型名称和 Base URL），不返回 API Key
    供前端 AI 设置面板只读展示
    """
    return APIResponse(
        code=200,
        data={
            "model": os.getenv("LLM_MODEL", "未配置"),
            "base_url": os.getenv("LLM_BASE_URL", "未配置"),
            "key_configured": bool(os.getenv("LLM_API_KEY", ""))
        }
    )

@router.post("/config", response_model=APIResponse)
def update_config(config: ConfigUpdate):
    try:
        update_app_config(config.key, config.value)
    except ValueError as e:
        return APIResponse(code=403, message=str(e))
    
    # Reload sentiment analyzer keywords if relevant
    if config.key in ['sentiment_bull_words', 'sentiment_bear_words']:
        from backend.app.services.sentiment_analyzer import sentiment_analyzer
        sentiment_analyzer.reload_keywords()
        
    return APIResponse(code=200, message="Config updated")

@router.post("/config/test-llm", response_model=APIResponse)
def test_llm_connection():
    """使用服务端环境变量中的 LLM 配置进行连通性测试，前端不需要传入任何 Key"""
    from backend.app.services.llm_service import llm_service
    try:
        llm_service.reload_config()
        llm_service.test_connection(llm_service.config)
        return APIResponse(code=200, message="连接测试成功")
    except Exception as e:
        return APIResponse(code=500, message=f"连接失败: {str(e)}")
