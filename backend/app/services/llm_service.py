import requests
import logging
from typing import Dict, Any, List
from backend.app.db.crud import get_app_config

logger = logging.getLogger(__name__)

class LLMService:
    def __init__(self):
        self.config = {}
        self.reload_config()

    def reload_config(self):
        raw_config = get_app_config()
        self.config = {
            "base_url": raw_config.get("llm_base_url", "https://api.openai.com/v1"),
            "api_key": raw_config.get("llm_api_key", ""),
            "model": raw_config.get("llm_model", "gpt-3.5-turbo"),
            "proxy": raw_config.get("llm_proxy", "")  # Add proxy support
        }

    def generate_sentiment_summary(self, symbol: str, metrics: Dict[str, Any], comments: List[Dict[str, Any]]) -> str:
        """
        调用 LLM 生成舆情摘要
        """
        self.reload_config()
        
        if not self.config["api_key"]:
            logger.warning("LLM API Key not configured, skipping AI summary.")
            raise ValueError("API Key 未配置，请在设置中添加 LLM API Key")

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
            headers = {
                "Authorization": f"Bearer {self.config['api_key']}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.config["model"],
                "messages": [
                    {"role": "system", "content": "You are a helpful financial assistant."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 100
            }
            
            # Handle non-OpenAI standard paths if needed, but assuming OpenAI-compatible
            url = f"{self.config['base_url'].rstrip('/')}/chat/completions"
            
            # Proxy settings
            proxies = {}
            if self.config.get("proxy"):
                proxies = {
                    "http": self.config["proxy"],
                    "https": self.config["proxy"]
                }

            logger.info(f"Calling LLM: {url} (Model: {self.config['model']})")
            
            # Increased timeout to 60s
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
                # 直接抛出包含详细信息的异常
                raise ValueError(error_msg)
            
            result = response.json()
            if 'choices' in result and len(result['choices']) > 0:
                content = result['choices'][0]['message']['content'].strip()
                return content
            else:
                logger.error(f"Unexpected LLM response format: {result}")
                raise ValueError("LLM 返回格式异常，未找到 choices")
            
        except requests.exceptions.Timeout:
            # Re-raise handled above, but catch again if needed or remove duplicate catch
            raise TimeoutError("请求 LLM 超时 (60s)，请检查网络连接")
        except requests.exceptions.RequestException as e:
            logger.error(f"LLM network error: {e}")
            raise ConnectionError(f"网络连接失败: {str(e)}")
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            raise e

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
