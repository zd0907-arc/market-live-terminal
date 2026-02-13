import requests
from bs4 import BeautifulSoup
import datetime
import logging
import time
from typing import List, Dict, Any
import sqlite3
import hashlib
from backend.app.db.database import get_db_connection
from backend.app.services.sentiment_analyzer import sentiment_analyzer

logger = logging.getLogger(__name__)

class SentimentCrawler:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

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
        
        if not time_str:
            return now.strftime("%Y-%m-%d %H:%M")
            
        try:
            # Case 1: "14:00" -> Today HH:MM
            if len(time_str) <= 5 and ':' in time_str:
                return f"{now.strftime('%Y-%m-%d')} {time_str}"
            
            # Case 2: "02-12 14:00" -> MM-DD HH:MM
            # 简单假设是今年，如果月份比当前月份大很多，可能是去年 (不太可能出现在第一页，除非很久没更新)
            # 或者如果月份比当前月份大，且当前是一月，那可能是去年的
            # 简单起见，直接拼当前年份
            # 改进：如果 parsed_date > now + 1 day，说明跨年了 (比如现在是 2026-01-01，帖子是 12-31)
            
            full_str = f"{current_year}-{time_str}"
            parsed_date = datetime.datetime.strptime(full_str, "%Y-%m-%d %H:%M")
            
            if parsed_date > now + datetime.timedelta(days=1):
                # 可能是去年
                full_str = f"{current_year - 1}-{time_str}"
            
            return full_str
        except Exception:
            return now.strftime("%Y-%m-%d %H:%M")

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
            r = requests.get(url, headers=self.headers, timeout=5)
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
                    # author_div = post.find("span", class_="l4") or post.find("div", class_="author")
                    time_div = post.find("span", class_="l5") or post.find("div", class_="pub_time")
                    
                    if title_div and read_div:
                        title = title_div.get_text().strip()
                        read_count = read_div.get_text().strip()
                        reply_count = reply_div.get_text().strip() if reply_div else 0
                        pub_time_str = time_div.get_text().strip() if time_div else ""
                        
                        full_time_str = self._parse_time(pub_time_str)
                        item_id = self._generate_id(stock_code, full_time_str, title)
                        
                        raw_item = {
                            "id": item_id,
                            "stock_code": stock_code,
                            "content": title,
                            "pub_time": full_time_str,
                            "read_count": read_count,
                            "reply_count": reply_count,
                            "crawl_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
            for item in comments:
                # 1. 清洗与分析
                processed = sentiment_analyzer.process_item(item)
                if not processed:
                    continue
                
                # 2. 插入 (IGNORE 重复)
                try:
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
            
            conn.commit()
        finally:
            conn.close()
            
        return saved_count

    def _parse_db_time(self, time_str: str) -> datetime.datetime:
        try:
            return datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M")

    def run_crawl(self, stock_code: str, mode: str = "manual"):
        """
        执行抓取流程
        :param mode: 'manual' (优先增量，快速响应) or 'scheduler' (优先深度，补全历史)
        """
        conn = get_db_connection()
        c = conn.cursor()
        
        # 1. 检查数据库中最早的评论时间
        c.execute("SELECT MIN(pub_time) FROM sentiment_comments WHERE stock_code = ?", (stock_code,))
        min_time_row = c.fetchone()
        conn.close()
        
        target_days = 14
        deep_crawl = False
        
        if not min_time_row or not min_time_row[0]:
            logger.info(f"[{stock_code}] No history found. Starting 14-day DEEP CRAWL...")
            deep_crawl = True
        else:
            if mode == "scheduler":
                try:
                    min_time = self._parse_db_time(min_time_row[0])
                    if (datetime.datetime.now() - min_time).days < target_days:
                        logger.info(f"[{stock_code}] History insufficient ({min_time}). Scheduler triggering DEEP CRAWL...")
                        deep_crawl = True
                    else:
                        logger.info(f"[{stock_code}] History sufficient. Scheduler triggering INCREMENTAL CRAWL...")
                except Exception as e:
                    logger.warning(f"Error parsing min_time: {e}. Defaulting to deep crawl.")
                    deep_crawl = True
            else:
                # Manual mode: Prefer incremental to be fast, unless empty
                logger.info(f"[{stock_code}] Manual trigger. Running INCREMENTAL CRAWL for speed.")
                deep_crawl = False

        total_new = 0
        page = 1
        # Manual mode max 20 pages (approx 20s), Scheduler/Deep max 50 pages
        max_pages = 50 if deep_crawl else (20 if mode == 'manual' else 5)
        
        while page <= max_pages:
            try:
                raw_data = self.fetch_guba_comments(stock_code, page=page)
                if not raw_data:
                    break
                
                new_count = self.save_comments(raw_data)
                total_new += new_count
                
                # 检查抓取到的最旧数据时间
                if raw_data:
                    # pub_time is usually YYYY-MM-DD HH:MM
                    last_item_time = self._parse_db_time(raw_data[-1]['pub_time'])
                    days_diff = (datetime.datetime.now() - last_item_time).days
                    
                    logger.info(f"[{stock_code}] Page {page}: Saved {new_count} new. Oldest: {last_item_time} ({days_diff} days ago)")
                    
                    # 停止条件
                    if deep_crawl:
                        if days_diff >= target_days:
                            logger.info(f"[{stock_code}] Reached 14-day target. Stopping.")
                            break
                    else:
                        # 增量模式：如果本页没有新数据，说明已经接上历史了
                        if new_count == 0:
                            logger.info(f"[{stock_code}] No new data on page {page}. Stopping incremental crawl.")
                            break
                else:
                    break
                
                page += 1
                time.sleep(1) # 礼貌间隔
                
            except Exception as e:
                logger.error(f"Crawl error on page {page}: {e}")
                break
                
        return total_new

sentiment_crawler = SentimentCrawler()
