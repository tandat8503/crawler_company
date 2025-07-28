#!/usr/bin/env python3
"""
Script để kiểm tra dữ liệu trong database
"""

from backend.db import get_companies, init_db
import pandas as pd

def check_database():
    print("=== Checking Database ===")
    
    # Khởi tạo database
    init_db()
    
    # Lấy tất cả dữ liệu
    companies = get_companies()
    print(f"Total companies in database: {len(companies)}")
    
    if companies:
        print("\n=== Sample Data ===")
        for i, company in enumerate(companies[:5]):  # Hiển thị 5 entries đầu
            print(f"\nCompany {i+1}:")
            print(f"  Company Name: {company.get('company_name', 'N/A')}")
            print(f"  Raised Date: {company.get('raised_date', 'N/A')}")
            print(f"  Source: {company.get('source', 'N/A')}")
            print(f"  Article URL: {company.get('article_url', 'N/A')}")
            print(f"  Amount Raised: {company.get('amount_raised', 'N/A')}")
            print(f"  Funding Round: {company.get('funding_round', 'N/A')}")
            print(f"  Crawl Date: {company.get('crawl_date', 'N/A')}")
        
        # Phân tích theo ngày
        print("\n=== Date Analysis ===")
        dates = [company.get('raised_date') for company in companies if company.get('raised_date')]
        if dates:
            print(f"Date range: {min(dates)} to {max(dates)}")
            print(f"Unique dates: {sorted(set(dates))}")
        else:
            print("No raised_date found in data")
            
        # Phân tích theo source
        print("\n=== Source Analysis ===")
        sources = [company.get('source') for company in companies if company.get('source')]
        source_counts = {}
        for source in sources:
            source_counts[source] = source_counts.get(source, 0) + 1
        for source, count in source_counts.items():
            print(f"  {source}: {count} entries")
    else:
        print("No data found in database")

if __name__ == "__main__":
    check_database() 