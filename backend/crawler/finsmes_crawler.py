import requests
from bs4 import BeautifulSoup
import csv
import os
import sys
from datetime import datetime, timedelta, date, timezone
from urllib.parse import urlparse
import json
import time
from collections import OrderedDict

# Thêm thư mục cha vào sys.path để import được các module
# sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

try:
    from thefuzz import fuzz
except ImportError:
    print('[WARNING] thefuzz is not installed. Please run: pip install thefuzz')
    fuzz = None

import pandas as pd
from .. import config
from ..deduplication import (
    normalize_company_name, normalize_amount, normalize_date,
    load_existing_entries
)
from ..search_utils import (
    find_company_website, find_company_linkedin, verify_company_info
)
from ..llm_utils import (
    extract_company_name_and_raised_date_llm, is_funding_article_llm, 
    extract_funding_info_llm, is_negative_news, extract_company_info_llm
)

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

CSV_FILE = config.CSV_FILE
HEADERS = config.HEADERS

# Add get_domain_root function
def get_domain_root(url):
    try:
        parsed = urlparse(url)
        host = parsed.netloc.replace('www.', '')
        parts = host.split('.')
        if len(parts) >= 2:
            return f"{parts[-2]}.{parts[-1]}"
        return host
    except Exception:
        return ""

def crawl_finsmes_usa(max_pages=5):
    """
    Crawl Finsmes USA articles.
    """
    articles = []
    for page in range(1, max_pages+1):
        url = f"https://www.finsmes.com/category/usa/page/{page}"
        try:
            logger.info(f"Fetching page {page}: {url}")
            resp = requests.get(url, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.find_all("div", class_="td-module-meta-info")
            logger.info(f"Page {page}: Found {len(cards)} cards with 'td-module-meta-info'")
            for meta in cards:
                h3 = meta.find("h3", class_="entry-title")
                a = h3.find("a") if h3 else None
                article_url = a["href"] if a else None
                title = a.get_text(strip=True) if a else ""
                date_div = meta.find("div", class_="td-editor-date")
                pub_date = date_div.get_text(strip=True) if date_div else ""
                if article_url:
                    articles.append({
                        "url": article_url,
                        "title": title,
                        "pub_date": pub_date
                    })
                    logger.info(f"Found article: {title} | {article_url} | {pub_date}")
            time.sleep(1)
        except Exception as e:
            logger.error(f"[ERROR][Finsmes] Page {page}: {e}")
    logger.info(f"Total Finsmes articles found: {len(articles)}")
    return articles

def extract_finsmes_article_detail(article_url):
    """
    Extract article detail from Finsmes.
    """
    try:
        resp = requests.get(article_url, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        content_div = soup.find("div", class_="td-post-content") or soup.find("div", class_="vc_column_container")
        article_text = ""
        if content_div:
            paragraphs = content_div.find_all("p")
            article_text = " ".join(p.get_text() for p in paragraphs)
        return soup, article_text
    except Exception as e:
        logger.error(f"[ERROR][Finsmes Detail] {article_url}: {e}")
        return None, ""

def extract_possible_company_website(soup, company_name):
    """
    Extract possible company website from article links.
    """
    norm_name = company_name.lower().replace(' ', '')
    for a in soup.find_all('a', href=True):
        text = a.get_text(strip=True)
        href = a['href']
        if norm_name and norm_name in text.lower().replace(' ', ''):
            if not any(x in href for x in ['techcrunch.com', 'linkedin.com', 'facebook.com', 'twitter.com', 'crunchbase.com', 'news.', '/news/']):
                return href
    return ""

# Xóa hoàn toàn các hàm save_to_csv, save_to_db, chỉ giữ lại crawl_finsmes trả về list entries

def crawl_finsmes():
    """
    Crawl Finsmes articles and extract company information.
    """
    today = date.today()
    min_date = today - timedelta(days=3)
    finsmes_articles = crawl_finsmes_usa(max_pages=5)
    logger.info(f'Found {len(finsmes_articles)} Finsmes articles.')
    existing_entries = load_existing_entries(CSV_FILE)
    unique_entries = {}
    for a in finsmes_articles:
        url = a['url']
        pub_date = a['pub_date']
        source = "Finsmes"
        try:
            soup, article_text = extract_finsmes_article_detail(url)
            if not article_text:
                logger.warning(f"[SKIP][NO CONTENT] {url}")
                continue
            title_tag = soup.find('h1') if soup else None
            title = title_tag.get_text(strip=True) if title_tag else ''
            if len(article_text) < 300:
                logger.info("[SKIP] Skipping article due to insufficient content.")
                continue
            if not is_funding_article_llm(article_text):
                logger.info(f"[SKIP][NOT FUNDING] Title: {title} | Date: {pub_date} | URL: {url}")
                continue
            info = extract_company_name_and_raised_date_llm(article_text, min_date.isoformat(), today.isoformat())
            if isinstance(info, list):
                infos = info
            else:
                infos = [info]
            for company_info in infos:
                company_name = company_info.get('company_name', '').strip()
                raised_date = company_info.get('raised_date', '').strip() or pub_date
                key = (normalize_company_name(company_name), url)
                if not company_name:
                    logger.warning(f"[SKIP][NO COMPANY NAME] Title: {title} | Date: {pub_date} | URL: {url}")
                    continue
                if key in existing_entries or key in unique_entries:
                    logger.info(f"[SKIP][DUPLICATE] {company_name} | {pub_date} | {url}")
                    continue
                website = find_company_website(company_name)
                linkedin = find_company_linkedin(company_name)
                crawl_date = today.isoformat()
                entry = {
                    'raised_date': raised_date,
                    'company_name': company_name,
                    'website': website,
                    'linkedin': linkedin,
                    'article_url': url,
                    'source': source,
                    'crawl_date': crawl_date
                }
                unique_entries[key] = entry
                logger.info(f"[ADD] {company_name} | {pub_date} | {url}")
        except Exception as e:
            logger.error(f"[ERROR] {url} | {e}")
    return list(unique_entries.values())

if __name__ == '__main__':
    logger.info("=== Finsmes Crawler ===")
    entries = crawl_finsmes()
    if entries:
        logger.info(f'Finsmes entries found: {len(entries)}')
    else:
        logger.info('No Finsmes entries found.')
    logger.info("Done. Check companies.csv for results.") 