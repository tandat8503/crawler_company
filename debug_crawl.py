#!/usr/bin/env python3
"""
Debug script để test crawl với logging chi tiết
"""

from backend.utils.logger import logger
from backend.crawler.techcrunch_crawler import get_article_links, crawl_techcrunch
from backend.llm_utils import has_funding_keywords, is_funding_article_llm
import requests
from bs4 import BeautifulSoup
from datetime import date, timedelta

def debug_article_processing():
    """Debug việc xử lý một bài viết cụ thể"""
    
    # Test với một bài viết thực tế
    test_url = "https://techcrunch.com/2025/07/22/openai-agreed-to-pay-oracle-30b-a-year-for-data-center-services/"
    
    logger.info(f"=== Debug Article Processing ===")
    logger.info(f"URL: {test_url}")
    
    try:
        # Fetch article
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; CompanyFundBot/1.0)'}
        resp = requests.get(test_url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Get title
        title_tag = soup.find('h1')
        title = title_tag.get_text(strip=True) if title_tag else ''
        logger.info(f"Title: {title}")
        
        # Get content
        article_body = soup.find('div', class_='entry-content')
        article_text = ""
        if article_body:
            paragraphs = article_body.find_all('p')
            article_text = " ".join(p.get_text() for p in paragraphs)
            logger.info(f"Content length: {len(article_text)} chars")
            logger.info(f"First 200 chars: {article_text[:200]}...")
        else:
            logger.warning("No article content found")
            return
        
        # Test keyword detection
        has_keywords = has_funding_keywords(article_text)
        logger.info(f"Has funding keywords: {has_keywords}")
        
        # Test LLM detection
        if has_keywords:
            is_funding = is_funding_article_llm(article_text)
            logger.info(f"LLM detected as funding: {is_funding}")
        else:
            logger.info("Skipping LLM test (no keywords)")
        
    except Exception as e:
        logger.error(f"Error processing article: {e}")

def debug_crawl_links():
    """Debug việc crawl links"""
    
    logger.info("=== Debug Crawl Links ===")
    
    today = date.today()
    min_date = today - timedelta(days=30)
    
    logger.info(f"Date range: {min_date} to {today}")
    
    try:
        links = get_article_links(min_date=min_date, max_pages=3)
        logger.info(f"Found {len(links)} articles")
        
        # Show first 5 articles
        for i, (url, pub_date) in enumerate(links[:5]):
            logger.info(f"Article {i+1}: {pub_date} - {url}")
            
    except Exception as e:
        logger.error(f"Error crawling links: {e}")

def debug_funding_keywords():
    """Debug hàm has_funding_keywords"""
    
    logger.info("=== Debug Funding Keywords ===")
    
    test_texts = [
        "OpenAI has raised $10 million in Series A funding",
        "A startup secures $5M investment from VCs",
        "Company launches new product",
        "Startup wins $1M competition prize",
        "OpenAI agreed to pay Oracle $30B for services"
    ]
    
    for i, text in enumerate(test_texts, 1):
        result = has_funding_keywords(text)
        logger.info(f"Test {i}: {result} - {text}")

if __name__ == "__main__":
    logger.info("🚀 Starting Debug Crawl...")
    
    debug_funding_keywords()
    debug_article_processing()
    debug_crawl_links()
    
    logger.info("✅ Debug completed!") 