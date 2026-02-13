import sys
import os
import time
import logging
from backend.app.services.sentiment_crawler import sentiment_crawler

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STOCKS = [
    ('300059', '东方财富'),
    ('600519', '贵州茅台'),
    ('600030', '中信证券'),
    ('300750', '宁德时代'),
    ('000833', '粤桂股份')
]

PAGES_PER_STOCK = 3
OUTPUT_FILE = "mined_comments.txt"

def main():
    logger.info("Starting sentiment keyword mining...")
    
    all_comments = []
    
    for code, name in STOCKS:
        logger.info(f"Crawling {name} ({code})...")
        for page in range(1, PAGES_PER_STOCK + 1):
            try:
                logger.info(f"  - Page {page}...")
                # 1. Fetch
                comments = sentiment_crawler.fetch_guba_comments(code, page=page)
                # 2. Save to DB (optional, but good for history)
                sentiment_crawler.save_comments(comments)
                
                # 3. Collect for text mining
                for c in comments:
                    all_comments.append(f"[{name}] {c['content']}")
                
                time.sleep(1) # Be polite
            except Exception as e:
                logger.error(f"Error crawling {code} page {page}: {e}")
                
    # Save to file
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("\n".join(all_comments))
        
    logger.info(f"Mining complete. Saved {len(all_comments)} comments to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
