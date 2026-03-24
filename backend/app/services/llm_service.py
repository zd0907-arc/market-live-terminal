import os
from pathlib import Path

import requests
import logging
import json
import re
from typing import Dict, Any, List

from dotenv import load_dotenv
from backend.app.db.crud import get_app_config

_repo_root = Path(__file__).resolve().parents[3]
load_dotenv(_repo_root / ".env.local", override=False)

logger = logging.getLogger(__name__)

class LLMService:
    def __init__(self):
        self.config = {}
        self.reload_config()

    def reload_config(self):
        """Key/Base URL 读环境变量；模型名允许 app_config 覆盖"""
        app_config = {}
        try:
            app_config = get_app_config() or {}
        except Exception as e:
            logger.warning("load app_config for llm model failed: %s", e)
        model_override = str(app_config.get("llm_model") or "").strip()
        self.config = {
            "base_url": os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
            "api_key": os.getenv("LLM_API_KEY", ""),
            "model": model_override or os.getenv("LLM_MODEL", "gpt-3.5-turbo"),
            "proxy": os.getenv("LLM_PROXY", "")
        }

    def _chat_complete(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.4,
        max_tokens: int = 400,
    ) -> str:
        self.reload_config()

        if not self.config["api_key"]:
            logger.warning("LLM API Key not configured, skipping request.")
            raise ValueError("API Key 未配置，请在设置中添加 LLM API Key")

        headers = {
            "Authorization": f"Bearer {self.config['api_key']}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.config["model"],
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        url = f"{self.config['base_url'].rstrip('/')}/chat/completions"

        proxies = {}
        if self.config.get("proxy"):
            proxies = {
                "http": self.config["proxy"],
                "https": self.config["proxy"]
            }

        logger.info(f"Calling LLM: {url} (Model: {self.config['model']})")

        import time
        start_time = time.time()
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=60, proxies=proxies)
            duration = time.time() - start_time
            logger.info(f"LLM request completed in {duration:.2f}s")
        except requests.exceptions.Timeout:
            duration = time.time() - start_time
            logger.error(f"LLM request timed out after {duration:.2f}s")
            raise TimeoutError("请求 LLM 超时 (60s)，请检查网络连接")

        if response.status_code != 200:
            error_msg = f"LLM API Error: {response.status_code} - {response.text}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        result = response.json()
        if 'choices' in result and len(result['choices']) > 0:
            return str(result['choices'][0]['message']['content'] or '').strip()

        logger.error(f"Unexpected LLM response format: {result}")
        raise ValueError("LLM 返回格式异常，未找到 choices")

    def generate_sentiment_summary(self, symbol: str, metrics: Dict[str, Any], comments: List[Dict[str, Any]]) -> str:
        """
        调用 LLM 生成舆情摘要
        """
        # Construct Prompt
        comments_text = "\n".join([f"- {c['content']} (情绪分:{c['sentiment_score']})" for c in comments[:20]])
        
        prompt = f"""
        你是一位专业的A股情绪分析师。请根据以下数据，对股票【{symbol}】的当前散户情绪进行简短、犀利的点评（50字以内）。
        
        【核心指标】
        - 情绪得分: {metrics['score']} (-10极度恐慌 ~ 10极度狂热)
        - 多空比: {metrics['bull_bear_ratio']}
        - 风险提示: {metrics['risk_warning']}
        
        【最新热评样本】
        {comments_text}
        
        【要求】
        1. 用词要符合A股游资风格（如：核按钮、接力、分歧、一致性）。
        2. 指出当前市场的主要担忧或期待。
        3. 不要废话，直接给结论。
        """

        try:
            return self._chat_complete(
                [
                    {"role": "system", "content": "You are a helpful financial assistant."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=100,
            )
        except requests.exceptions.Timeout:
            # Re-raise handled above, but catch again if needed or remove duplicate catch
            raise TimeoutError("请求 LLM 超时 (60s)，请检查网络连接")
        except requests.exceptions.RequestException as e:
            logger.error(f"LLM network error: {e}")
            raise ConnectionError(f"网络连接失败: {str(e)}")
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            raise e

    def generate_daily_sentiment_analysis(
        self,
        symbol: str,
        trade_date: str,
        samples: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not samples:
            raise ValueError("缺少用于解读的评论样本")

        sample_lines: List[str] = []
        for idx, item in enumerate(samples[:20], start=1):
            title = str(item.get("title") or "").strip()
            content = str(item.get("content") or "").strip()
            body = content if content and content != title else title
            read_count = int(item.get("view_count") or item.get("read_count") or 0)
            reply_count = int(item.get("reply_count") or 0)
            sample_lines.append(
                f"{idx}. 阅读={read_count} 评论={reply_count}\n标题：{title or '无标题'}\n内容：{body[:1200]}"
            )

        prompt = f"""
你是一位A股游资风格的散户舆情分析师。请基于以下 {symbol} 在 {trade_date} 的股吧高价值样本，输出严格 JSON。

要求：
1. sentiment_score 取值范围 -100 到 100，正数偏多，负数偏空。
2. direction_label 只能是：偏多、偏空、分歧、中性。
3. consensus_strength 取值 0 到 100，越高代表观点越一致。
4. emotion_temperature 取值 0 到 100，越高代表情绪越激烈（FOMO/恐慌都算高）。
5. risk_tag 只能是：FOMO追涨、恐慌踩踏、高热分歧、低热观望、叙事发酵。
6. summary_text 用 40~80 字总结当天散户主叙事与交易风险。
7. 只输出 JSON，不要输出任何解释或 Markdown。

样本：
{chr(10).join(sample_lines)}

JSON 结构：
{{
  "sentiment_score": 0,
  "direction_label": "中性",
  "consensus_strength": 0,
  "emotion_temperature": 0,
  "risk_tag": "低热观望",
  "summary_text": ""
}}
""".strip()

        raw = self._chat_complete(
            [
                {"role": "system", "content": "你是专业的A股散户舆情分析助手，只能输出 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=300,
        )

        match = re.search(r"\{.*\}", raw, re.S)
        if not match:
            raise ValueError(f"LLM 未返回合法 JSON: {raw}")
        payload = json.loads(match.group(0))

        score = max(-100, min(100, int(round(float(payload.get("sentiment_score", 0))))))
        direction = str(payload.get("direction_label") or "中性")
        if direction not in {"偏多", "偏空", "分歧", "中性"}:
            direction = "中性"
        consensus = max(0, min(100, int(round(float(payload.get("consensus_strength", 0))))))
        temperature = max(0, min(100, int(round(float(payload.get("emotion_temperature", 0))))))
        risk_tag = str(payload.get("risk_tag") or "低热观望")
        if risk_tag not in {"FOMO追涨", "恐慌踩踏", "高热分歧", "低热观望", "叙事发酵"}:
            risk_tag = "低热观望"
        summary_text = str(payload.get("summary_text") or "").strip()

        return {
            "sentiment_score": score,
            "direction_label": direction,
            "consensus_strength": consensus,
            "emotion_temperature": temperature,
            "risk_tag": risk_tag,
            "summary_text": summary_text,
            "raw_response": raw,
        }

    def test_connection(self, config: Dict[str, Any]) -> bool:
        """
        测试 LLM 连接
        """
        base_url = config.get("base_url", "https://api.openai.com/v1")
        api_key = config.get("api_key", "")
        model = config.get("model", "gpt-3.5-turbo")
        proxy = config.get("proxy", "")

        if not api_key:
            raise ValueError("API Key is missing")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # 构造一个极简的请求来验证连通性
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": "Hello"}
            ],
            "max_tokens": 5
        }
        
        url = f"{base_url.rstrip('/')}/chat/completions"
        
        proxies = {}
        if proxy:
            proxies = {
                "http": proxy,
                "https": proxy
            }
            
        try:
            logger.info(f"Testing LLM Connection: {url}")
            # 设置较短的超时时间 (10秒)
            response = requests.post(url, json=payload, headers=headers, timeout=10, proxies=proxies)
            
            if response.status_code != 200:
                raise ValueError(f"API Error: {response.status_code} - {response.text}")
                
            return True
        except Exception as e:
            logger.error(f"LLM Connection Test Failed: {e}")
            raise e

llm_service = LLMService()
