#!/usr/bin/env python3
"""
Main entry point for Company RaiseFund application
"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.crawler.crawl_all import run_crawlers, CRAWLERS, save_entries_bulk

def main():
    """Main function to run the crawler"""
    # Lấy danh sách crawlers có sẵn
    available_crawlers = list(CRAWLERS.keys())
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command in available_crawlers:
            print(f"Running {command.capitalize()} crawler only...")
            results = run_crawlers([command], parallel=False)
            save_entries_bulk(results)
        elif command == 'all':
            print("Running all available crawlers...")
            results = run_crawlers(available_crawlers, parallel=True)
            save_entries_bulk(results)
        else:
            print(f"Usage: python main.py [{'|'.join(available_crawlers)}|all]")
            print("  techcrunch: Crawl TechCrunch only")
            print("  finsmes: Crawl Finsmes only")
            print("  all: Crawl all crawlers in parallel")
    else:
        print("Default: Running all available crawlers...")
        results = run_crawlers(available_crawlers, parallel=True)
        save_entries_bulk(results)

if __name__ == "__main__":
    main() 