import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.db.database import init_db
from backend.app.routers import watchlist, market, analysis, config, monitor, sentiment
from backend.app.services.collector import collector
from backend.app.services.monitor import monitor as sentiment_monitor
from backend.app.scheduler import init_scheduler
from datetime import datetime
import logging
import urllib3

# 禁用不安全的HTTPS警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AlphaData Local Server", 
    description="本地金融数据服务 - 为前端提供历史资金流向与博弈分析数据",
    version="3.0.3"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(watchlist.router, prefix="/api", tags=["Watchlist"])
app.include_router(market.router, prefix="/api", tags=["Market Data"])
app.include_router(analysis.router, prefix="/api", tags=["Analysis"])
app.include_router(config.router, prefix="/api", tags=["Config"])
app.include_router(monitor.router, prefix="/api/monitor", tags=["Monitor"])
app.include_router(sentiment.router, prefix="/api", tags=["Retail Sentiment"])

@app.get("/api/health")
def api_health_check():
    return {
        "status": "ok",
        "service": "AlphaData Backend API",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

@app.on_event("startup")
async def startup_event():
    init_db()
    collector.start()
    sentiment_monitor.start()
    init_scheduler()
    for route in app.routes:
        print(f"Registered Route: {route.path} [{route.methods}]")

@app.on_event("shutdown")
async def shutdown_event():
    collector.stop()
    sentiment_monitor.stop()

@app.get("/")
def health_check():
    return {
        "status": "running", 
        "service": "AlphaData Backend v2", 
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "docs": "http://127.0.0.1:8000/docs"
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
