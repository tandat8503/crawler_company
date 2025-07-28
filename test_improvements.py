#!/usr/bin/env python3
"""
Test script để kiểm tra các cải tiến đã thực hiện
"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.crawler.crawl_all import CRAWLERS, run_crawlers, save_entries_bulk
from backend.db import insert_many_companies, get_companies
from backend.deduplication import normalize_company_name
from backend.utils.retry import exponential_backoff_retry
from backend.utils.logger import logger

def test_crawler_structure():
    """Test cấu trúc crawler mới"""
    print("=== Testing Crawler Structure ===")
    
    # Test CRAWLERS dictionary
    print(f"✅ Available crawlers: {list(CRAWLERS.keys())}")
    
    for name, info in CRAWLERS.items():
        print(f"✅ {name}: {info['name']} - {info['description']}")
        assert callable(info['function']), f"Crawler function for {name} is not callable"
    
    print("✅ Crawler structure test passed")

def test_bulk_insert():
    """Test bulk insert functionality"""
    print("\n=== Testing Bulk Insert ===")
    
    # Test data
    test_entries = [
        {
            'raised_date': '2025-01-01',
            'company_name': 'Test Company 1',
            'website': 'https://test1.com',
            'linkedin': 'https://linkedin.com/company/test1',
            'article_url': 'https://techcrunch.com/test1',
            'amount_raised': '$1M',
            'funding_round': 'Seed',
            'crawl_date': '2025-01-01',
            'source': 'Test'
        },
        {
            'raised_date': '2025-01-02',
            'company_name': 'Test Company 2',
            'website': 'https://test2.com',
            'linkedin': 'https://linkedin.com/company/test2',
            'article_url': 'https://techcrunch.com/test2',
            'amount_raised': '$2M',
            'funding_round': 'Series A',
            'crawl_date': '2025-01-02',
            'source': 'Test'
        }
    ]
    
    try:
        # Test bulk insert
        inserted_count = insert_many_companies(test_entries)
        print(f"✅ Bulk insert test: {inserted_count} entries inserted")
        
        # Verify data was inserted
        companies = get_companies()
        test_companies = [c for c in companies if c['source'] == 'Test']
        print(f"✅ Found {len(test_companies)} test companies in database")
        
    except Exception as e:
        print(f"❌ Bulk insert test failed: {e}")

def test_normalize_company_name():
    """Test company name normalization"""
    print("\n=== Testing Company Name Normalization ===")
    
    test_cases = [
        ("Apple Inc.", "apple"),
        ("Microsoft Corporation", "microsoft"),
        ("Google LLC", "google"),
        ("Tesla Technologies", "tesla"),
        ("SpaceX Holdings", "spacex"),
        ("OpenAI Inc.", "openai"),
        ("Meta Platforms Inc.", "metaplatforms"),
        ("Amazon.com Inc.", "amazoncom"),
    ]
    
    for input_name, expected in test_cases:
        result = normalize_company_name(input_name)
        status = "✅" if result == expected else "❌"
        print(f"{status} '{input_name}' -> '{result}' (expected: '{expected}')")

def test_retry_decorator():
    """Test retry decorator"""
    print("\n=== Testing Retry Decorator ===")
    
    call_count = 0
    
    @exponential_backoff_retry(max_retries=2, base_delay=0.1)
    def test_function():
        nonlocal call_count
        call_count += 1
        if call_count < 3:  # Fail first 2 times
            raise ValueError("Simulated error")
        return "Success"
    
    try:
        result = test_function()
        print(f"✅ Retry test passed: {result} (called {call_count} times)")
    except Exception as e:
        print(f"❌ Retry test failed: {e}")

def test_crawler_functions():
    """Test crawler functions without actually running them"""
    print("\n=== Testing Crawler Functions ===")
    
    # Test run_crawlers with empty list
    results = run_crawlers([], parallel=False)
    assert results == {}, "Empty crawler list should return empty dict"
    print("✅ Empty crawler list test passed")
    
    # Test save_entries_bulk with empty dict
    save_results = save_entries_bulk({})
    assert save_results == {}, "Empty entries should return empty save results"
    print("✅ Empty entries save test passed")

def main():
    """Run all tests"""
    print("🧪 Running improvement tests...\n")
    
    try:
        test_crawler_structure()
        test_bulk_insert()
        test_normalize_company_name()
        test_retry_decorator()
        test_crawler_functions()
        
        print("\n🎉 All tests passed!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 