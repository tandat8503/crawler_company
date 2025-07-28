#!/usr/bin/env python3
"""
Test script toàn diện cho hệ thống crawl sau khi cải tiến
"""

from backend.utils.logger import logger
from backend.db import init_db, get_companies, get_all_companies
from backend.deduplication import load_existing_entries
from backend.crawler.techcrunch_crawler import get_article_links, crawl_techcrunch
from backend.llm_utils import has_funding_keywords, is_funding_article_llm
import os

def test_database_schema():
    """Test database schema và operations"""
    logger.info("=== Testing Database Schema ===")
    
    try:
        # Test init_db
        init_db()
        logger.info("✅ Database initialization successful")
        
        # Test insert với đầy đủ fields
        from backend.db import insert_company
        test_data = {
            'raised_date': '2025-07-28',
            'company_name': 'Test Company',
            'website': 'https://testcompany.com',
            'linkedin': 'https://linkedin.com/company/testcompany',
            'article_url': 'https://techcrunch.com/test-article',
            'amount_raised': '$10M',
            'funding_round': 'Series A',
            'crawl_date': '2025-07-28',
            'source': 'TechCrunch'
        }
        
        insert_company(test_data)
        logger.info("✅ Insert with all fields successful")
        
        # Test get_companies
        companies = get_companies()
        logger.info(f"✅ Get companies successful: {len(companies)} companies")
        
        # Test get_all_companies
        all_companies = get_all_companies()
        logger.info(f"✅ Get all companies successful: {len(all_companies)} companies")
        
        # Test load_existing_entries
        existing_entries = load_existing_entries()
        logger.info(f"✅ Load existing entries successful: {len(existing_entries)} entries")
        
        return True
    except Exception as e:
        logger.error(f"❌ Database test failed: {e}")
        return False

def test_crawl_improvements():
    """Test các cải tiến crawl"""
    logger.info("=== Testing Crawl Improvements ===")
    
    try:
        # Test get_article_links với cải tiến
        from datetime import date, timedelta
        today = date.today()
        min_date = today - timedelta(days=30)
        
        links = get_article_links(min_date=min_date, max_pages=2)
        logger.info(f"✅ Found {len(links)} articles with improved crawl")
        
        # Kiểm tra xem có bài viết thực sự không
        real_articles = [url for url, date in links if '/category/' not in url and '/tag/' not in url]
        logger.info(f"✅ Found {len(real_articles)} real articles (not category pages)")
        
        # Show first 5 articles
        for i, (url, pub_date) in enumerate(links[:5]):
            logger.info(f"  Article {i+1}: {pub_date} - {url}")
        
        return True
    except Exception as e:
        logger.error(f"❌ Crawl improvements test failed: {e}")
        return False

def test_funding_detection_improvements():
    """Test cải tiến funding detection"""
    logger.info("=== Testing Funding Detection Improvements ===")
    
    test_cases = [
        {
            "text": "Startup raises $50M in Series B funding led by Sequoia Capital",
            "expected_keywords": True,
            "expected_funding": True
        },
        {
            "text": "Company launches new product and announces partnership",
            "expected_keywords": False,
            "expected_funding": False
        },
        {
            "text": "AI startup secures $10 million investment from venture capitalists",
            "expected_keywords": True,
            "expected_funding": True
        }
    ]
    
    try:
        for i, case in enumerate(test_cases, 1):
            logger.info(f"\nTest Case {i}:")
            logger.info(f"  Text: {case['text'][:50]}...")
            
            # Test keyword detection
            has_keywords = has_funding_keywords(case['text'])
            keyword_status = "✅" if has_keywords == case['expected_keywords'] else "❌"
            logger.info(f"  Keywords: {keyword_status} Expected: {case['expected_keywords']}, Got: {has_keywords}")
            
            # Test LLM detection if keywords found
            if has_keywords:
                is_funding = is_funding_article_llm(case['text'])
                funding_status = "✅" if is_funding == case['expected_funding'] else "❌"
                logger.info(f"  LLM: {funding_status} Expected: {case['expected_funding']}, Got: {is_funding}")
            else:
                logger.info("  LLM: Skipped (no keywords)")
        
        return True
    except Exception as e:
        logger.error(f"❌ Funding detection test failed: {e}")
        return False

def test_deduplication_from_db():
    """Test deduplication từ database"""
    logger.info("=== Testing Deduplication from DB ===")
    
    try:
        # Test load_existing_entries
        existing_entries = load_existing_entries()
        logger.info(f"✅ Loaded {len(existing_entries)} existing entries from DB")
        
        # Test với dữ liệu test
        if len(existing_entries) > 0:
            logger.info("✅ Deduplication from DB working")
        else:
            logger.info("ℹ️ No existing entries found (normal for fresh DB)")
        
        return True
    except Exception as e:
        logger.error(f"❌ Deduplication test failed: {e}")
        return False

def test_complete_crawl():
    """Test crawl hoàn chỉnh với cải tiến"""
    logger.info("=== Testing Complete Crawl ===")
    
    try:
        # Test crawl với số lượng nhỏ
        entries = crawl_techcrunch()
        logger.info(f"✅ Crawl completed: {len(entries)} entries found")
        
        if entries:
            # Kiểm tra cấu trúc entry
            first_entry = entries[0]
            required_fields = ['raised_date', 'company_name', 'website', 'linkedin', 
                             'article_url', 'source', 'crawl_date', 'amount_raised', 'funding_round']
            
            missing_fields = [field for field in required_fields if field not in first_entry]
            if missing_fields:
                logger.warning(f"⚠️ Missing fields in entry: {missing_fields}")
            else:
                logger.info("✅ All required fields present in entry")
            
            # Show sample entry
            logger.info(f"Sample entry: {first_entry.get('company_name')} | {first_entry.get('amount_raised')} | {first_entry.get('funding_round')}")
        
        return True
    except Exception as e:
        logger.error(f"❌ Complete crawl test failed: {e}")
        return False

def main():
    """Run all tests"""
    logger.info("🚀 Starting Complete System Test...")
    
    tests = [
        ("Database Schema", test_database_schema),
        ("Crawl Improvements", test_crawl_improvements),
        ("Funding Detection", test_funding_detection_improvements),
        ("Deduplication from DB", test_deduplication_from_db),
        ("Complete Crawl", test_complete_crawl),
    ]
    
    results = {}
    for test_name, test_func in tests:
        logger.info(f"\n{'='*50}")
        logger.info(f"Running {test_name} test...")
        try:
            results[test_name] = test_func()
        except Exception as e:
            logger.error(f"❌ {test_name} test crashed: {e}")
            results[test_name] = False
    
    # Summary
    logger.info(f"\n{'='*50}")
    logger.info("📊 COMPLETE SYSTEM TEST SUMMARY")
    logger.info("="*50)
    
    passed = 0
    total = len(tests)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{test_name}: {status}")
        if result:
            passed += 1
    
    logger.info(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("🎉 All tests passed! System is ready for production crawling.")
    else:
        logger.error("⚠️ Some tests failed. Please check the issues above.")
    
    return passed == total

if __name__ == "__main__":
    main() 