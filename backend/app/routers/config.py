from fastapi import APIRouter
from backend.app.models.schemas import APIResponse, AppConfig
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

@router.post("/config", response_model=APIResponse)
def update_config(key: str, value: str):
    update_app_config(key, value)
    return APIResponse(code=200, message="Config updated")
