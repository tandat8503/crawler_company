#!/usr/bin/env python3
"""
Test script để kiểm tra việc chuyển đổi sang Tavily
"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.search_utils import (
    search_tavily, find_company_website, find_company_linkedin,
    normalize_name_for_matching, get_url_match_score, verify_company_info
)
from backend.utils.logger import logger

def test_tavily_api():
    """Test Tavily API connection"""
    print("=== Testing Tavily API ===")
    
    # Test basic search
    results = search_tavily("OpenAI company", max_results=3)
    print(f"✅ Tavily API test: {len(results)} results found")
    
    if results:
        print(f"✅ First result: {results[0].get('title', 'No title')}")
        print(f"✅ First URL: {results[0].get('url', 'No URL')}")
    
    return len(results) > 0

def test_company_name_normalization():
    """Test company name normalization"""
    print("\n=== Testing Company Name Normalization ===")
    
    test_cases = [
        ("OpenAI Inc.", "openai"),
        ("Microsoft Corporation", "microsoft"),
        ("Google LLC", "google"),
        ("Tesla Technologies", "tesla"),
        ("SpaceX Holdings", "spacex"),
    ]
    
    for input_name, expected in test_cases:
        result = normalize_name_for_matching(input_name)
        status = "✅" if result == expected else "❌"
        print(f"{status} '{input_name}' -> '{result}' (expected: '{expected}')")

def test_url_matching():
    """Test URL matching logic"""
    print("\n=== Testing URL Matching ===")
    
    test_cases = [
        ("OpenAI", "https://openai.com", "OpenAI - Artificial Intelligence Research", 90),
        ("Microsoft", "https://microsoft.com", "Microsoft - Official Homepage", 95),
        ("Tesla", "https://tesla.com", "Tesla - Electric Cars", 90),
        ("Random Company", "https://random.com", "Random Website", 30),
    ]
    
    for company_name, url, title, expected_min_score in test_cases:
        score = get_url_match_score(company_name, url, title)
        status = "✅" if score >= expected_min_score else "❌"
        print(f"{status} '{company_name}' vs '{url}' -> score: {score} (expected >= {expected_min_score})")

def test_find_company_website():
    """Test find_company_website function"""
    print("\n=== Testing Find Company Website ===")
    
    test_companies = [
        "OpenAI",
        "Microsoft", 
        "Tesla",
        "SpaceX"
    ]
    
    for company in test_companies:
        website = find_company_website(company)
        status = "✅" if website else "❌"
        print(f"{status} '{company}' -> '{website}'")

def test_find_company_linkedin():
    """Test find_company_linkedin function"""
    print("\n=== Testing Find Company LinkedIn ===")
    
    test_companies = [
        "OpenAI",
        "Microsoft",
        "Tesla", 
        "SpaceX"
    ]
    
    for company in test_companies:
        linkedin = find_company_linkedin(company)
        status = "✅" if linkedin else "❌"
        print(f"{status} '{company}' -> '{linkedin}'")

def test_verify_company_info():
    """Test verify_company_info function"""
    print("\n=== Testing Verify Company Info ===")
    
    test_cases = [
        ("OpenAI", "", ""),
        ("Microsoft", "https://microsoft.com", ""),
        ("Tesla", "", "https://linkedin.com/company/tesla"),
    ]
    
    for company_name, website, linkedin in test_cases:
        result = verify_company_info(company_name, website, linkedin)
        print(f"✅ '{company_name}' -> website: '{result['website']}', linkedin: '{result['linkedin']}'")

def test_social_media_filtering():
    """Test social media and news site filtering"""
    print("\n=== Testing Social Media Filtering ===")
    
    from backend.search_utils import is_social_media_or_news_site
    
    test_urls = [
        ("https://linkedin.com/company/openai", True),
        ("https://twitter.com/openai", True),
        ("https://techcrunch.com/article", True),
        ("https://openai.com", False),
        ("https://microsoft.com", False),
    ]
    
    for url, expected in test_urls:
        result = is_social_media_or_news_site(url)
        status = "✅" if result == expected else "❌"
        print(f"{status} '{url}' -> {result} (expected: {expected})")

def main():
    """Run all Tavily migration tests"""
    print("🧪 Running Tavily migration tests...\n")
    
    try:
        # Test basic functionality
        test_tavily_api()
        test_company_name_normalization()
        test_url_matching()
        test_social_media_filtering()
        
        # Test search functions (these might take longer)
        print("\n🔄 Testing search functions (this may take a while)...")
        test_find_company_website()
        test_find_company_linkedin()
        test_verify_company_info()
        
        print("\n🎉 All Tavily migration tests completed!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 