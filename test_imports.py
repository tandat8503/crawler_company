#!/usr/bin/env python3
"""
Test script để kiểm tra các import có hoạt động đúng không
"""

def test_imports():
    print("=== Testing imports ===")
    
    try:
        from backend import config
        print("✅ backend.config imported successfully")
    except Exception as e:
        print(f"❌ backend.config import failed: {e}")
    
    try:
        from backend.db import init_db, insert_company, get_companies
        print("✅ backend.db imported successfully")
    except Exception as e:
        print(f"❌ backend.db import failed: {e}")
    
    try:
        from backend.search_utils import search_company_website_tavily, search_company_linkedin_tavily
        print("✅ backend.search_utils imported successfully")
    except Exception as e:
        print(f"❌ backend.search_utils import failed: {e}")
    
    try:
        from backend.llm_utils import extract_company_name_and_raised_date_llm, is_funding_article_llm
        print("✅ backend.llm_utils imported successfully")
    except Exception as e:
        print(f"❌ backend.llm_utils import failed: {e}")
    
    try:
        from backend.deduplication import normalize_company_name, load_existing_entries
        print("✅ backend.deduplication imported successfully")
    except Exception as e:
        print(f"❌ backend.deduplication import failed: {e}")
    
    try:
        from backend.crawler.techcrunch_crawler import crawl_techcrunch
        print("✅ backend.crawler.techcrunch_crawler imported successfully")
    except Exception as e:
        print(f"❌ backend.crawler.techcrunch_crawler import failed: {e}")
    
    try:
        from backend.crawler.finsmes_crawler import crawl_finsmes
        print("✅ backend.crawler.finsmes_crawler imported successfully")
    except Exception as e:
        print(f"❌ backend.crawler.finsmes_crawler import failed: {e}")
    
    print("\n=== Testing database ===")
    try:
        from backend.db import init_db, get_companies
        init_db()
        companies = get_companies()
        print(f"✅ Database initialized successfully, found {len(companies)} companies")
    except Exception as e:
        print(f"❌ Database test failed: {e}")

if __name__ == "__main__":
    test_imports() 