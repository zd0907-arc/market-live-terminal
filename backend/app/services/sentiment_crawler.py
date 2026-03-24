import requests
from bs4 import BeautifulSoup
import datetime
import json
import logging
import re
import time
from typing import List, Dict, Any, Optional
import sqlite3
import hashlib
from urllib.parse import urljoin
from backend.app.db.database import get_db_connection
from backend.app.services.sentiment_analyzer import sentiment_analyzer

logger = logging.getLogger(__name__)

class SentimentCrawler:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.guba_timeout = 8

    def _generate_id(self, stock_code: str, pub_time: str, title: str) -> str:
        """生成唯一ID: md5(code + time + title)"""
        raw_str = f"{stock_code}_{pub_time}_{title}"
        return hashlib.md5(raw_str.encode('utf-8')).hexdigest()

    def _parse_time(self, time_str: str) -> str:
        """
        解析时间，处理跨年逻辑
        格式: "02-12 14:00" or "14:00"
        """
        now = datetime.datetime.now()
        current_year = now.year
        
        time_str = time_str.strip()
        if not time_str:
            return now.strftime("%Y-%m-%d %H:%M")
            
        try:
            # Case 1: "14:00" -> Today HH:MM
            if len(time_str) <= 5 and ':' in time_str:
                return f"{now.strftime('%Y-%m-%d')} {time_str}"
            
            # Case 2: "02-12 14:00" -> MM-DD HH:MM
            full_str = f"{current_year}-{time_str}"
            parsed_date = datetime.datetime.strptime(full_str, "%Y-%m-%d %H:%M")
            
            if parsed_date > now + datetime.timedelta(days=1):
                # 可能是去年
                full_str = f"{current_year - 1}-{time_str}"
            
            return full_str
        except Exception as e:
            logger.warning(f"Time parse error for '{time_str}': {e}")
            return now.strftime("%Y-%m-%d %H:%M")

    def _normalize_prefixed_symbol(self, stock_code: str) -> str:
        code = str(stock_code or "").strip().lower()
        if code.startswith(("sh", "sz", "bj")):
            return code
        if len(code) == 6 and code.isdigit():
            if code.startswith(("600", "601", "603", "605", "688", "689", "900")):
                return f"sh{code}"
            if code.startswith(("000", "001", "002", "003", "300", "301", "200")):
                return f"sz{code}"
            return f"bj{code}"
        return code

    def _normalize_plain_code(self, stock_code: str) -> str:
        code = str(stock_code or "").strip().lower()
        return code[2:] if code.startswith(("sh", "sz", "bj")) and len(code) == 8 else code

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            if value in (None, ""):
                return default
            return int(float(value))
        except Exception:
            return default

    def _safe_datetime_text(self, value: Any) -> Optional[str]:
        if value in (None, ""):
            return None
        text = str(value).strip()
        if not text:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.datetime.strptime(text, fmt).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                continue
        try:
            numeric = float(value)
            if numeric > 10_000_000_000:
                numeric = numeric / 1000.0
            return datetime.datetime.fromtimestamp(numeric).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return text

    def _parse_json_object_from_html(self, html: str, var_name: str) -> Optional[Dict[str, Any]]:
        marker = f"var {var_name}="
        start = html.find(marker)
        if start < 0:
            return None
        start = start + len(marker)
        end = html.find("</script>", start)
        if end < 0:
            return None
        payload = html[start:end].strip().rstrip(";")
        try:
            return json.loads(payload)
        except Exception as e:
            logger.warning("parse %s json failed: %s", var_name, e)
            return None

    def _make_event_id(self, source: str, source_event_id: str) -> str:
        raw = f"{source}:{source_event_id}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def _clean_text_content(self, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if "<" in text and ">" in text:
            try:
                text = BeautifulSoup(text, "html.parser").get_text("\n", strip=True)
            except Exception:
                pass
        return text.strip()

    def _normalize_guba_url(self, raw_href: Optional[str]) -> Optional[str]:
        href = str(raw_href or "").strip()
        if not href:
            return None
        if href.startswith("//"):
            return f"https:{href}"
        if href.startswith("http://") or href.startswith("https://"):
            return href
        return urljoin("https://guba.eastmoney.com/", href)

    def _extract_post_id_from_href(self, href: Optional[str]) -> Optional[str]:
        text = str(href or "").strip()
        if not text:
            return None
        for pattern in [
            r"/news,\d{6},(\d+)\.html",
            r"caifuhao\.eastmoney\.com/news/(\d+)",
            r"postid=(\d+)",
        ]:
            match = re.search(pattern, text)
            if match:
                return str(match.group(1))
        return None

    def _clean_caifuhao_body(self, title: str, text_content: str) -> str:
        lines = [line.strip() for line in str(text_content or "").splitlines() if str(line or "").strip()]
        if not lines:
            return title
        cleaned: List[str] = []
        skip_tokens = (
            "返回",
            "点赞",
            "评论",
            "收藏",
            "举报",
            "分享",
            "大",
            "中",
            "小",
            "追加内容",
        )
        for idx, line in enumerate(lines):
            compact = re.sub(r"\s+", "", line)
            if idx == 0 and title and compact == re.sub(r"\s+", "", title):
                continue
            if re.fullmatch(r"\d{4}年\d{2}月\d{2}日\s*\d{2}:\d{2}", compact):
                continue
            if any(compact == token for token in skip_tokens):
                continue
            if compact in {"点赞0", "评论0", "收藏0"}:
                continue
            if re.fullmatch(r"[\u4e00-\u9fff]{1,8}省", compact):
                continue
            if re.fullmatch(r"(作者|来源)[:：].{0,30}", compact):
                continue
            cleaned.append(line)

        if not cleaned:
            return title
        body = "\n".join(cleaned).strip()
        if not body:
            return title
        if title and body.startswith(title):
            return body
        if title:
            return f"{title}\n{body}".strip()
        return body

    def fetch_guba_comments(self, stock_code: str, page: int = 1) -> List[Dict[str, Any]]:
        """
        抓取东方财富股吧评论
        :param stock_code: 股票代码
        :param page: 页码 (默认1)
        """
        # 东财URL规则: 
        # 首页: list,stock_code.html
        # 第N页: list,stock_code_N.html
        if page > 1:
            url = f"http://guba.eastmoney.com/list,{stock_code}_{page}.html"
        else:
            url = f"http://guba.eastmoney.com/list,{stock_code}.html"
            
        logger.info(f"Crawling {url}...")
        
        try:
            r = self.session.get(url, headers=self.headers, timeout=self.guba_timeout)
            r.encoding = 'utf-8'
            soup = BeautifulSoup(r.text, 'html.parser')
            
            comments = []
            
            # 尝试方案 A: 新版列表结构
            posts = soup.find_all("div", class_="articleh")
            
            # 如果方案 A 没找到，尝试方案 B: 旧版 table tr
            if not posts:
                posts = soup.find_all("tr", class_="listitem")

            for post in posts:
                try:
                    # 过滤掉置顶、广告
                    if post.find("em", class_="settop") or post.find("em", class_="ad"):
                        continue
                    
                    # 提取字段
                    read_div = post.find("span", class_="l1") or post.find("div", class_="read")
                    reply_div = post.find("span", class_="l2") or post.find("div", class_="reply")
                    title_div = post.find("span", class_="l3") or post.find("div", class_="title")
                    author_div = post.find("span", class_="l4") or post.find("div", class_="author")
                    time_div = post.find("span", class_="l5") or post.find("div", class_="pub_time") or post.find("div", class_="update")
                    
                    if title_div and read_div:
                        title = title_div.get_text().strip()
                        link_el = title_div.find("a")
                        raw_href = link_el.get("href") if link_el else None
                        raw_url = None
                        if raw_href:
                            raw_url = self._normalize_guba_url(raw_href)
                        read_count = read_div.get_text().strip()
                        reply_count = reply_div.get_text().strip() if reply_div else 0
                        author_name = author_div.get_text().strip() if author_div else None
                        pub_time_str = time_div.get_text().strip() if time_div else ""
                        
                        full_time_str = self._parse_time(pub_time_str)
                        item_id = self._generate_id(stock_code, full_time_str, title)
                        post_id = link_el.get("data-postid") if link_el else None
                        if not post_id:
                            post_id = self._extract_post_id_from_href(raw_href)
                        post_type = link_el.get("data-posttype") if link_el else None
                        normalized_symbol = self._normalize_prefixed_symbol(stock_code)
                        
                        raw_item = {
                            "id": item_id,
                            "stock_code": normalized_symbol,
                            "content": title,
                            "pub_time": full_time_str,
                            "read_count": read_count,
                            "reply_count": reply_count,
                            "crawl_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "author_name": author_name,
                            "source": "guba",
                            "event_type": "post",
                            "thread_id": item_id,
                            "parent_id": None,
                            "raw_url": raw_url,
                            "source_event_id": str(post_id or (item_id if not raw_href else raw_href.strip("/"))),
                            "post_id": str(post_id or ""),
                            "post_type": str(post_type or ""),
                        }
                        
                        comments.append(raw_item)
                except Exception as e:
                    logger.warning(f"Error parsing post: {e}")
                    continue
                    
            return comments
        except Exception as e:
            logger.error(f"Crawler error: {e}")
            return []

    def save_comments(self, comments: List[Dict[str, Any]]):
        """
        保存评论到数据库 (增量保存)
        """
        if not comments:
            return 0
            
        conn = get_db_connection()
        c = conn.cursor()
        saved_count = 0
        
        try:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS sentiment_events (
                    event_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    thread_id TEXT,
                    parent_id TEXT,
                    content TEXT NOT NULL,
                    author_name TEXT,
                    pub_time DATETIME,
                    crawl_time DATETIME,
                    view_count INTEGER,
                    reply_count INTEGER,
                    like_count INTEGER,
                    repost_count INTEGER,
                    raw_url TEXT,
                    source_event_id TEXT,
                    extra_json TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_sentiment_events_source_event
                ON sentiment_events (source, source_event_id);
            """)
            for item in comments:
                # 1. 清洗与分析
                processed = sentiment_analyzer.process_item(item)
                if not processed:
                    continue
                
                # 2. 插入 (IGNORE 重复)
                try:
                    if str(item.get("source") or "guba") == "guba" and str(item.get("event_type") or "post") == "post":
                        c.execute("""
                            INSERT OR IGNORE INTO sentiment_comments 
                            (id, stock_code, content, pub_time, read_count, reply_count, sentiment_score, heat_score, crawl_time)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            processed['id'],
                            processed['stock_code'],
                            processed['content'],
                            processed['pub_time'],
                            processed['read_count'],
                            processed['reply_count'],
                            processed['sentiment_score'],
                            processed['heat_score'],
                            processed['crawl_time']
                        ))
                        if c.rowcount > 0:
                            saved_count += 1
                except sqlite3.Error as e:
                    logger.error(f"DB Insert error: {e}")

                try:
                    extra_payload = item.get("extra_json")
                    if isinstance(extra_payload, (dict, list)):
                        extra_payload = json.dumps(extra_payload, ensure_ascii=False)
                    if not extra_payload:
                        extra_payload = json.dumps({"legacy_list_crawl": True}, ensure_ascii=False)

                    event_id = str(item.get("event_id") or processed['id'])
                    source = str(item.get('source') or 'guba')
                    source_event_id = str(item.get('source_event_id') or event_id)
                    payload = (
                        source,
                        processed['stock_code'],
                        str(item.get('event_type') or 'post'),
                        str(item.get('thread_id') or event_id),
                        item.get('parent_id'),
                        processed['content'],
                        item.get('author_name'),
                        processed['pub_time'],
                        processed['crawl_time'],
                        self._safe_int(item.get('view_count', processed.get('read_count')), 0),
                        self._safe_int(item.get('reply_count', processed.get('reply_count')), 0),
                        self._safe_int(item.get('like_count'), 0),
                        self._safe_int(item.get('repost_count'), 0),
                        item.get('raw_url'),
                        extra_payload,
                    )
                    c.execute("""
                        UPDATE sentiment_events
                        SET source=?, symbol=?, event_type=?, thread_id=?, parent_id=?, content=?, author_name=?, pub_time=?, crawl_time=?,
                            view_count=?, reply_count=?, like_count=?, repost_count=?, raw_url=?, extra_json=?
                        WHERE event_id=? OR (source=? AND source_event_id=?)
                    """, (
                        *payload,
                        event_id,
                        source,
                        source_event_id,
                    ))
                    if c.rowcount == 0:
                        c.execute("""
                            INSERT OR IGNORE INTO sentiment_events
                            (event_id, source, symbol, event_type, thread_id, parent_id, content, author_name, pub_time, crawl_time,
                             view_count, reply_count, like_count, repost_count, raw_url, source_event_id, extra_json)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            event_id,
                            source,
                            processed['stock_code'],
                            str(item.get('event_type') or 'post'),
                            str(item.get('thread_id') or event_id),
                            item.get('parent_id'),
                            processed['content'],
                            item.get('author_name'),
                            processed['pub_time'],
                            processed['crawl_time'],
                            self._safe_int(item.get('view_count', processed.get('read_count')), 0),
                            self._safe_int(item.get('reply_count', processed.get('reply_count')), 0),
                            self._safe_int(item.get('like_count'), 0),
                            self._safe_int(item.get('repost_count'), 0),
                            item.get('raw_url'),
                            source_event_id,
                            extra_payload,
                        ))
                except sqlite3.Error as e:
                    logger.error(f"DB Event Insert error: {e}")
            
            conn.commit()
        finally:
            conn.close()
            
        return saved_count

    def _parse_db_time(self, time_str: str) -> datetime.datetime:
        try:
            return datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M")

    def fetch_guba_post_detail(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        raw_url = str(item.get("raw_url") or "").strip()
        post_id = str(item.get("post_id") or item.get("source_event_id") or "").strip()
        if not raw_url or not post_id or "guba.eastmoney.com/news" not in raw_url:
            return None

        try:
            response = self.session.get(raw_url, headers={**self.headers, "Referer": raw_url}, timeout=self.guba_timeout)
            response.encoding = "utf-8"
            article = self._parse_json_object_from_html(response.text, "post_article")
            if not article:
                return None

            content = self._clean_text_content(
                article.get("post_content") or article.get("post_abstract") or article.get("post_title") or item.get("content") or ""
            )
            publish_time = self._safe_datetime_text(article.get("post_publish_time")) or self._safe_datetime_text(item.get("pub_time"))
            thread_event_id = self._make_event_id("guba", f"post:{post_id}")
            return {
                **item,
                "event_id": thread_event_id,
                "id": thread_event_id,
                "source": "guba",
                "stock_code": self._normalize_prefixed_symbol(item.get("stock_code") or ""),
                "event_type": "post",
                "thread_id": thread_event_id,
                "parent_id": None,
                "source_event_id": f"post:{post_id}",
                "content": content,
                "pub_time": publish_time or item.get("pub_time"),
                "author_name": (
                    ((article.get("post_user") or {}).get("user_nickname"))
                    or item.get("author_name")
                ),
                "view_count": self._safe_int(article.get("post_click_count"), self._safe_int(item.get("read_count"), 0)),
                "reply_count": self._safe_int(article.get("post_comment_count"), self._safe_int(item.get("reply_count"), 0)),
                "like_count": self._safe_int(article.get("post_like_count"), 0),
                "repost_count": self._safe_int(article.get("post_forward_count"), 0),
                "extra_json": {
                    "post_id": post_id,
                    "post_type": article.get("post_type"),
                    "stockbar_code": ((article.get("post_guba") or {}).get("stockbar_code")),
                    "stockbar_name": ((article.get("post_guba") or {}).get("stockbar_name")),
                    "detail_fetched": True,
                },
            }
        except Exception as e:
            logger.warning("fetch_guba_post_detail failed for %s: %s", raw_url, e)
            return None

    def fetch_caifuhao_post_detail(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        raw_url = str(item.get("raw_url") or "").strip()
        if not raw_url or "caifuhao.eastmoney.com/news/" not in raw_url:
            return None
        try:
            response = self.session.get(raw_url, headers={**self.headers, "Referer": raw_url}, timeout=self.guba_timeout)
            response.encoding = "utf-8"
            soup = BeautifulSoup(response.text, "html.parser")

            article_root = soup.select_one("div.article")
            if not article_root:
                return None

            text_content = self._clean_text_content(article_root.get_text("\n", strip=True))
            title_match = re.search(r'articletitle:"([^"]+)"', response.text)
            author_match = re.search(r'nickname:"([^"]+)"', response.text)
            postid_match = re.search(r'postId:"?(\d+)"?', response.text)
            time_match = re.search(r'(\d{4}年\d{2}月\d{2}日\s+\d{2}:\d{2})', text_content)
            publish_time = None
            if time_match:
                try:
                    publish_time = datetime.datetime.strptime(time_match.group(1), "%Y年%m月%d日 %H:%M").strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    publish_time = None

            post_id = str(postid_match.group(1) if postid_match else item.get("post_id") or item.get("source_event_id") or "").strip()
            source_event_id = f"post:{post_id}" if post_id else str(item.get("source_event_id") or item.get("id"))
            event_id = self._make_event_id("guba", source_event_id)
            title = self._clean_text_content(title_match.group(1) if title_match else item.get("content") or "")
            content = self._clean_caifuhao_body(title=title, text_content=text_content)

            return {
                **item,
                "event_id": event_id,
                "id": event_id,
                "source": "guba",
                "stock_code": self._normalize_prefixed_symbol(item.get("stock_code") or ""),
                "event_type": "post",
                "thread_id": event_id,
                "parent_id": None,
                "source_event_id": source_event_id,
                "content": content,
                "pub_time": publish_time or self._safe_datetime_text(item.get("pub_time")) or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "author_name": self._clean_text_content(author_match.group(1) if author_match else item.get("author_name") or ""),
                "view_count": self._safe_int(item.get("read_count"), 0),
                "reply_count": self._safe_int(item.get("reply_count"), 0),
                "like_count": 0,
                "repost_count": 0,
                "extra_json": {
                    "detail_source": "caifuhao",
                    "post_id": post_id,
                    "detail_fetched": True,
                },
            }
        except Exception as e:
            logger.warning("fetch_caifuhao_post_detail failed for %s: %s", raw_url, e)
            return None

    def _extract_reply_items_from_payload(self, payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            return []
        for key in ["re", "reply_list", "result", "list", "data", "user_jxreply_list", "fake_reply_list"]:
            value = payload.get(key)
            if isinstance(value, list):
                return value
        nested = payload.get("result")
        if isinstance(nested, dict):
            for key in ["re", "reply_list", "list", "data"]:
                value = nested.get(key)
                if isinstance(value, list):
                    return value
        return []

    def fetch_guba_replies(self, stock_code: str, post_id: str, thread_event_id: str, raw_url: str, expected_count: int = 0) -> List[Dict[str, Any]]:
        if not post_id:
            return []

        endpoints = [
            ("ArticleNewReplyList", {"postid": post_id, "sort": 1, "sorttype": 1, "p": 1, "ps": min(max(expected_count or 10, 10), 50)}),
            ("ArticleHotReply", {"postid": post_id}),
        ]
        replies: List[Dict[str, Any]] = []
        plain_code = self._normalize_plain_code(stock_code)

        for endpoint_name, params in endpoints:
            endpoint = f"https://gbapi.eastmoney.com/reply/api/Reply/{endpoint_name}"
            try:
                response = self.session.get(
                    endpoint,
                    params=params,
                    headers={**self.headers, "Referer": raw_url},
                    timeout=self.guba_timeout,
                )
                payload = response.json()
                message = str(payload.get("me") or "")
                if "系统繁忙" in message:
                    continue
                items = self._extract_reply_items_from_payload(payload)
                if not items:
                    continue

                for reply in items:
                    source_reply_id = str(
                        reply.get("reply_id")
                        or reply.get("comment_id")
                        or reply.get("id")
                        or reply.get("replyid")
                        or ""
                    ).strip()
                    content = self._clean_text_content(
                        reply.get("reply_content")
                        or reply.get("content")
                        or reply.get("reply_text")
                        or reply.get("reply")
                        or ""
                    )
                    if not source_reply_id or not content:
                        continue
                    author_name = (
                        reply.get("user_nickname")
                        or reply.get("reply_user_nickname")
                        or reply.get("author_name")
                        or ((reply.get("reply_user") or {}).get("user_nickname") if isinstance(reply.get("reply_user"), dict) else None)
                    )
                    pub_time = self._safe_datetime_text(
                        reply.get("reply_time")
                        or reply.get("comment_time")
                        or reply.get("post_publish_time")
                        or reply.get("ctime")
                        or reply.get("created_at")
                    ) or self._safe_datetime_text(reply.get("display_time"))
                    replies.append(
                        {
                            "event_id": self._make_event_id("guba", f"reply:{source_reply_id}"),
                            "id": self._make_event_id("guba", f"reply:{source_reply_id}"),
                            "source": "guba",
                            "stock_code": self._normalize_prefixed_symbol(stock_code),
                            "event_type": "reply",
                            "thread_id": thread_event_id,
                            "parent_id": thread_event_id,
                            "content": content,
                            "pub_time": pub_time or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "crawl_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "read_count": 0,
                            "reply_count": 0,
                            "view_count": 0,
                            "like_count": self._safe_int(reply.get("like_count") or reply.get("reply_like_count"), 0),
                            "repost_count": 0,
                            "author_name": author_name,
                            "raw_url": raw_url,
                            "source_event_id": f"reply:{source_reply_id}",
                            "extra_json": {
                                "reply_api": endpoint_name,
                                "raw_reply_id": source_reply_id,
                                "raw_symbol": plain_code,
                            },
                        }
                    )
                if replies:
                    break
            except Exception as e:
                logger.warning("fetch_guba_replies failed for post %s via %s: %s", post_id, endpoint_name, e)
                continue

        return replies

    def _enrich_guba_batch(self, raw_data: List[Dict[str, Any]], mode: str = "manual", page: int = 1) -> List[Dict[str, Any]]:
        if not raw_data:
            return []
        enriched: List[Dict[str, Any]] = []
        detail_limit = 12 if mode == "manual" and page == 1 else 8 if mode == "view" else 6
        detail_budget = 0

        for item in raw_data:
            current = dict(item)
            post_id = str(current.get("post_id") or current.get("source_event_id") or "")
            raw_url = str(current.get("raw_url") or "")
            should_fetch_detail = bool(post_id and raw_url and detail_budget < detail_limit)
            detail = None
            if should_fetch_detail and "guba.eastmoney.com/news" in raw_url:
                detail = self.fetch_guba_post_detail(current)
            elif should_fetch_detail and "caifuhao.eastmoney.com/news/" in raw_url:
                detail = self.fetch_caifuhao_post_detail(current)
            if detail:
                current = detail
                detail_budget += 1
            current.setdefault("event_id", current.get("id"))
            current.setdefault("source_event_id", f"post:{post_id}" if post_id else current.get("id"))
            enriched.append(current)
        return enriched

    def _page_signature(self, raw_data: List[Dict[str, Any]]) -> str:
        ids = [str(item.get("source_event_id") or item.get("id") or "") for item in raw_data[:10]]
        return "|".join(ids)

    def _run_paged_fetch(
        self,
        stock_code: str,
        *,
        mode: str,
        max_pages: int,
        stop_when_no_new: bool = False,
        stop_before_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        total_new = 0
        page = 1
        seen_signatures = set()
        oldest_seen: Optional[str] = None

        while page <= max_pages:
            try:
                raw_data = self.fetch_guba_comments(stock_code, page=page)
                if not raw_data:
                    break

                signature = self._page_signature(raw_data)
                if signature in seen_signatures:
                    logger.info("[%s] duplicated page signature detected on page=%s, stop", stock_code, page)
                    break
                seen_signatures.add(signature)

                batch_to_save = self._enrich_guba_batch(raw_data, mode=mode, page=page)
                new_count = self.save_comments(batch_to_save)
                total_new += new_count

                oldest_item_time = self._parse_db_time(raw_data[-1]["pub_time"])
                oldest_seen = oldest_item_time.strftime("%Y-%m-%d %H:%M:%S")
                logger.info(
                    "[%s] page=%s mode=%s saved=%s oldest=%s",
                    stock_code,
                    page,
                    mode,
                    new_count,
                    oldest_seen,
                )

                if stop_before_date and oldest_item_time.strftime("%Y-%m-%d") < stop_before_date:
                    logger.info("[%s] reached stop_before_date=%s on page=%s", stock_code, stop_before_date, page)
                    break

                if stop_when_no_new and new_count == 0:
                    logger.info("[%s] no new data on page=%s, stop", stock_code, page)
                    break

                page += 1
                time.sleep(0.6)
            except Exception as e:
                logger.error("Crawl error on page %s: %s", page, e)
                break

        return {
            "new_count": total_new,
            "pages": page if page <= max_pages else max_pages,
            "oldest_seen": oldest_seen,
        }

    def run_crawl(self, stock_code: str, mode: str = "manual"):
        """
        轻量增量抓取：
        - manual/view: 用于页面打开后的快速补抓
        - scheduler/pre_open/post_close/nightly: 用于星标股每日补齐
        """
        normalized = self._normalize_prefixed_symbol(stock_code)
        if mode in {"scheduler", "pre_open", "post_close"}:
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            result = self._run_paged_fetch(
                normalized,
                mode="scheduler",
                max_pages=8,
                stop_before_date=today,
            )
            return int(result["new_count"])
        if mode == "nightly":
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            result = self._run_paged_fetch(
                normalized,
                mode="scheduler",
                max_pages=20,
                stop_before_date=today,
            )
            return int(result["new_count"])

        result = self._run_paged_fetch(
            normalized,
            mode="view" if mode == "view" else "manual",
            max_pages=3,
            stop_when_no_new=True,
        )
        return int(result["new_count"])

    def backfill_history(self, stock_code: str, target_days: int = 20, max_pages: int = 80) -> Dict[str, Any]:
        normalized = self._normalize_prefixed_symbol(stock_code)
        cutoff_date = (datetime.datetime.now() - datetime.timedelta(days=max(1, int(target_days)))).strftime("%Y-%m-%d")
        result = self._run_paged_fetch(
            normalized,
            mode="scheduler",
            max_pages=max_pages,
            stop_before_date=cutoff_date,
        )
        return {
            "symbol": normalized,
            "target_days": int(target_days),
            "new_count": int(result["new_count"]),
            "pages": int(result["pages"]),
            "oldest_seen": result["oldest_seen"],
            "completed": bool(result["oldest_seen"] and str(result["oldest_seen"])[:10] <= cutoff_date),
        }

sentiment_crawler = SentimentCrawler()
