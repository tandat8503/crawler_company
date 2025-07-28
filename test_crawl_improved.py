#!/usr/bin/env python3
"""
Test script để kiểm tra crawl với cải tiến
"""

from backend.utils.logger import logger
from backend.crawler.techcrunch_crawler import get_article_links
from datetime import date, timedelta

def test_improved_crawl():
    """Test crawl với cải tiến"""
    
    logger.info("=== Testing Improved Crawl ===")
    
    today = date.today()
    min_date = today - timedelta(days=30)
    
    logger.info(f"Date range: {min_date} to {today}")
    
    try:
        # Test crawl với cải tiến
        links = get_article_links(min_date=min_date, max_pages=2)
        logger.info(f"Found {len(links)} articles")
        
        # Show first 10 articles
        for i, (url, pub_date) in enumerate(links[:10]):
            logger.info(f"Article {i+1}: {pub_date} - {url}")
            
        # Phân tích kết quả
        if len(links) > 0:
            logger.info("✅ Crawl successful - found actual articles")
            
            # Kiểm tra xem có bài viết funding không
            funding_keywords = ['funding', 'investment', 'raises', 'raised', 'series']
            funding_count = 0
            
            for url, pub_date in links[:5]:  # Kiểm tra 5 bài đầu
                if any(keyword in url.lower() for keyword in funding_keywords):
                    funding_count += 1
                    logger.info(f"Potential funding article: {url}")
            
            logger.info(f"Potential funding articles found: {funding_count}")
            
        else:
            logger.warning("⚠️ No articles found")
            
    except Exception as e:
        logger.error(f"Error in improved crawl: {e}")

def test_single_category():
    """Test crawl từ một category cụ thể"""
    
    logger.info("=== Testing Single Category ===")
    
    import requests
    from bs4 import BeautifulSoup
    
    category_url = 'https://techcrunch.com/category/startups/'
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; CompanyFundBot/1.0)'}
        resp = requests.get(category_url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Tìm tất cả links
        all_links = soup.find_all('a', href=True)
        article_links = []
        
        for link in all_links:
            url = link['href']
            if '/2025/' in url and '/category/' not in url and '/tag/' not in url:
                article_links.append(url)
        
        logger.info(f"Found {len(article_links)} potential articles")
        
        # Show first 5
        for i, url in enumerate(article_links[:5]):
            logger.info(f"Article {i+1}: {url}")
            
    except Exception as e:
        logger.error(f"Error testing single category: {e}")

if __name__ == "__main__":
    logger.info("🚀 Starting Improved Crawl Test...")
    
    test_single_category()
    test_improved_crawl()
    
    logger.info("✅ Improved crawl test completed!") 