from fastapi import APIRouter, HTTPException, BackgroundTasks
from starlette.concurrency import run_in_threadpool
from backend.app.services.sentiment_crawler import sentiment_crawler
from backend.app.db.database import get_db_connection
from backend.app.models.schemas import APIResponse
import pandas as pd
from datetime import datetime, timedelta
import logging

router = APIRouter(prefix="/sentiment", tags=["Retail Sentiment"])
logger = logging.getLogger(__name__)

@router.post("/crawl/{symbol}")
async def trigger_crawl(symbol: str):
    """
    触发抓取任务 (同步等待模式)
    """
    try:
        # 在线程池中运行以避免阻塞事件循环
        new_count = await run_in_threadpool(sentiment_crawler.run_crawl, symbol, mode="manual")
        return {"status": "success", "message": f"Crawled {new_count} new comments", "new_count": new_count}
    except Exception as e:
        logger.error(f"Crawl failed for {symbol}: {e}")
        return {"status": "error", "message": str(e)}

@router.get("/dashboard/{symbol}")
def get_dashboard_data(symbol: str):
    """
    获取情绪仪表盘数据
    """
    conn = get_db_connection()
    
    # 1. 获取最近 24 小时的统计
    # 截止时间
    now = datetime.now()
    cutoff_time = (now - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
    
    query = f"""
    SELECT sentiment_score, heat_score, content, read_count 
    FROM sentiment_comments 
    WHERE stock_code = ? AND pub_time > ?
    ORDER BY heat_score DESC
    """
    
    df = pd.read_sql(query, conn, params=(symbol, cutoff_time))
    conn.close()
    
    if df.empty:
        return {
            "score": 0,
            "status": "暂无数据",
            "bull_bear_ratio": 0,
            "summary": "过去24小时未监测到有效评论，请点击抓取按钮更新数据。",
            "risk_warning": "无",
            "details": {"bull_count": 0, "bear_count": 0, "total_count": 0}
        }
        
    # 2. 计算基础指标
    bull_count = len(df[df['sentiment_score'] == 1])
    bear_count = len(df[df['sentiment_score'] == -1])
    total_count = len(df)
    
    # 多空比 (避免除零)
    ratio = round(bull_count / (bear_count + 1), 2)
    
    # 3. 模拟 LLM 分析 (Mock) -> 升级为真实 LLM
    # 真实场景这里应该调用 OpenAI/DeepSeek API，传入 df.head(20) 的 content
    
    score = 0
    status = "多空分歧"
    summary = ""
    risk = "中"
    
    if ratio > 2.5:
        score = 8
        status = "极度狂热"
        summary = "散户情绪高涨，评论区充斥着‘涨停’、‘连板’等关键词。一致性过强，需警惕主力反手砸盘。"
        risk = "高 (一致性获利兑现风险)"
    elif ratio > 1.2:
        score = 5
        status = "温和看多"
        summary = "大部分散户持乐观态度，认为回调即买点。市场承接力较好。"
        risk = "中 (正常波动)"
    elif ratio < 0.5:
        score = -7
        status = "恐慌绝望"
        summary = "评论区充斥谩骂与割肉言论，散户心态崩盘。情绪接近冰点，可能是反弹契机。"
        risk = "低 (情绪冰点，可能反转)"
    elif ratio < 0.8:
        score = -3
        status = "弱势震荡"
        summary = "空头略占上风，散户信心不足，观望情绪浓厚。"
        risk = "中偏高 (阴跌风险)"
    else:
        score = 0
        status = "多空平衡"
        summary = "多空双方分歧较大，互道傻X。方向未明，建议等待主力表态。"
        risk = "中 (方向选择期)"
        
    # 尝试调用真实 LLM 生成更精准的摘要
    try:
        from backend.app.services.llm_service import llm_service
        metrics = {
            "score": score,
            "bull_bear_ratio": ratio,
            "risk_warning": risk
        }
        # 取前20条热评
        top_comments = df.head(20).to_dict(orient='records')
        ai_summary = llm_service.generate_sentiment_summary(symbol, metrics, top_comments)
        if ai_summary:
            summary = ai_summary
    except Exception as e:
        logger.warning(f"Failed to generate AI summary: {e}")

    return {
        "score": score,
        "status": status,
        "bull_bear_ratio": ratio,
        "summary": summary,
        "risk_warning": risk,
        "details": {
            "bull_count": bull_count, 
            "bear_count": bear_count, 
            "total_count": total_count
        }
    }

@router.post("/summary/{symbol}")
def generate_summary(symbol: str):
    """
    手动触发 AI 摘要生成并保存
    """
    conn = get_db_connection()
    try:
        # 1. 获取最近 24h 统计数据
        cutoff_time = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        df = pd.read_sql("""
            SELECT content, sentiment_score, heat_score, pub_time 
            FROM sentiment_comments 
            WHERE stock_code = ? AND pub_time > ? 
            ORDER BY heat_score DESC LIMIT 20
        """, conn, params=(symbol, cutoff_time))
        
        if df.empty:
            return APIResponse(code=200, message="No data for summary", data={"content": "暂无足够数据生成摘要。"})

        # 计算基础指标
        total_score = df['sentiment_score'].sum()
        bull_count = len(df[df['sentiment_score'] > 0])
        bear_count = len(df[df['sentiment_score'] < 0])
        ratio = round(bull_count / (bear_count + 1), 2)
        score = min(max(total_score, -10), 10)
        
        # 2. 调用 LLM
        from backend.app.services.llm_service import llm_service
        metrics = {
            "score": score,
            "bull_bear_ratio": ratio,
            "risk_warning": "AI 分析中"
        }
        top_comments = df.to_dict(orient='records')
        
        ai_content = llm_service.generate_sentiment_summary(symbol, metrics, top_comments)
        
        if not ai_content:
            return APIResponse(code=500, message="生成的摘要内容为空")
            
        # 3. 存库
        cursor = conn.cursor()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO sentiment_summaries (stock_code, content, model_used, created_at) VALUES (?, ?, ?, ?)",
            (symbol, ai_content, llm_service.config.get('model', 'unknown'), current_time)
        )
        conn.commit()
        
        return APIResponse(code=200, message="Summary generated", data={"content": ai_content, "created_at": current_time})
        
    except Exception as e:
        logger.error(f"Generate summary error: {e}")
        # Return 200 with error message in body so frontend can display it gracefully
        return APIResponse(code=500, message=str(e))
    finally:
        conn.close()

@router.get("/summary/history/{symbol}")
def get_summary_history(symbol: str):
    """
    获取历史 AI 摘要
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, content, created_at, model_used FROM sentiment_summaries WHERE stock_code = ? ORDER BY created_at DESC LIMIT 10",
            (symbol,)
        )
        rows = cursor.fetchall()
        result = [
            {"id": r[0], "content": r[1], "created_at": r[2], "model": r[3]} 
            for r in rows
        ]
        return result
    finally:
        conn.close()

@router.get("/trend/{symbol}")
def get_sentiment_trend(symbol: str, interval: str = "72h"):
    """
    获取情绪趋势数据
    :param interval: '72h' (按小时) or '14d' (按天)
    """
    conn = get_db_connection()
    
    if interval == "14d":
        # 按天聚合 (最近14天)
        cutoff_time = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")
        query = """
        SELECT 
            strftime('%Y-%m-%d', pub_time) as time_bucket,
            SUM(heat_score) as total_heat,
            COUNT(*) as post_count,
            SUM(CASE WHEN sentiment_score > 0 THEN 1 ELSE 0 END) as bull_vol,
            SUM(CASE WHEN sentiment_score < 0 THEN 1 ELSE 0 END) as bear_vol
        FROM sentiment_comments
        WHERE stock_code = ? AND pub_time > ?
        GROUP BY time_bucket
        ORDER BY time_bucket ASC
        """
    else:
        # 按小时聚合 (默认72H)
        cutoff_time = (datetime.now() - timedelta(hours=72)).strftime("%Y-%m-%d %H:%M:%S")
        query = """
        SELECT 
            strftime('%Y-%m-%d %H:00', pub_time) as time_bucket,
            SUM(heat_score) as total_heat,
            COUNT(*) as post_count,
            SUM(CASE WHEN sentiment_score > 0 THEN 1 ELSE 0 END) as bull_vol,
            SUM(CASE WHEN sentiment_score < 0 THEN 1 ELSE 0 END) as bear_vol
        FROM sentiment_comments
        WHERE stock_code = ? AND pub_time > ?
        GROUP BY time_bucket
        ORDER BY time_bucket ASC
        """
    
    try:
        df = pd.read_sql(query, conn, params=(symbol, cutoff_time))
        # 计算多空比
        df['bull_bear_ratio'] = df.apply(lambda row: round(row['bull_vol'] / (row['bear_vol'] + 1), 2), axis=1)
        return df.to_dict(orient='records')
    except Exception as e:
        logger.error(f"Trend query error: {e}")
        return []
    finally:
        conn.close()

@router.get("/comments/{symbol}")
def get_recent_comments(symbol: str, limit: int = 50):
    """
    获取最近的评论列表 (原始数据)
    """
    conn = get_db_connection()
    # 简单的查询最近 limit 条
    query = """
    SELECT id, content, pub_time, read_count, reply_count, sentiment_score, heat_score 
    FROM sentiment_comments 
    WHERE stock_code = ? 
    ORDER BY pub_time DESC, heat_score DESC 
    LIMIT ?
    """
    
    try:
        # 使用 pandas 读取或者直接 cursor fetchall
        # 这里用 pandas 方便转 dict
        df = pd.read_sql(query, conn, params=(symbol, limit))
        return df.to_dict(orient='records')
    except Exception as e:
        logger.error(f"Comments query error: {e}")
        return []
    finally:
        conn.close()
