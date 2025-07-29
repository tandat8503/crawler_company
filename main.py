#!/usr/bin/env python3
"""
Main entry point for the company funding crawler
"""

import sys
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any

import config
from db import insert_company, insert_many_companies, init_db
from techcrunch_crawler import crawl_techcrunch
from finsmes_crawler import crawl_finsmes
from utils.logger import logger

# Dictionary to manage available crawlers
CRAWLERS = {
    'techcrunch': {
        'function': crawl_techcrunch,
        'name': 'TechCrunch',
        'description': 'Crawl TechCrunch for funding news'
    },
    'finsmes': {
        'function': crawl_finsmes,
        'name': 'Finsmes',
        'description': 'Crawl Finsmes for funding news'
    }
}

def run_single_crawler(crawler_name: str) -> List[Dict[str, Any]]:
    """
    Run a specific crawler and return results
    
    Args:
        crawler_name: Crawler name (key in CRAWLERS)
    
    Returns:
        List of entries from crawler
    """
    if crawler_name not in CRAWLERS:
        logger.error(f"Crawler '{crawler_name}' does not exist")
        return []
    
    crawler_info = CRAWLERS[crawler_name]
    logger.info(f"=== Starting {crawler_info['name']} Crawler ===")
    
    try:
        entries = crawler_info['function']()
        if entries:
            logger.info(f"Found {len(entries)} records from {crawler_info['name']}")
            return entries
        else:
            logger.info(f'No new {crawler_info["name"]} records found.')
            return []
    except Exception as e:
        logger.error(f"Error crawling {crawler_info['name']}: {e}")
        logger.exception(f"Error details for {crawler_info['name']}:")
        return []

def run_crawlers(crawler_names: List[str] = None, parallel: bool = True) -> Dict[str, List[Dict[str, Any]]]:
    """
    Run one or multiple crawlers
    
    Args:
        crawler_names: List of crawler names to run. If None, run all
        parallel: Whether to run in parallel
    
    Returns:
        Dict with key as crawler name, value as list of entries
    """
    if crawler_names is None:
        crawler_names = list(CRAWLERS.keys())
    
    # Initialize database
    try:
        init_db()
        logger.info("=== Database initialized successfully ===")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        return {}
    
    results = {}
    
    if parallel and len(crawler_names) > 1:
        # Run in parallel
        logger.info(f"Running {len(crawler_names)} crawlers in parallel...")
        with ThreadPoolExecutor(max_workers=len(crawler_names)) as executor:
            future_to_crawler = {
                executor.submit(run_single_crawler, name): name 
                for name in crawler_names
            }
            
            for future in as_completed(future_to_crawler):
                crawler_name = future_to_crawler[future]
                try:
                    entries = future.result()
                    results[crawler_name] = entries
                except Exception as e:
                    logger.error(f"Error running crawler {crawler_name}: {e}")
                    results[crawler_name] = []
    else:
        # Run sequentially
        for crawler_name in crawler_names:
            entries = run_single_crawler(crawler_name)
            results[crawler_name] = entries
    
    return results

def save_entries_bulk(entries_by_crawler: Dict[str, List[Dict[str, Any]]]) -> Dict[str, int]:
    """
    Save all entries to database using bulk insert
    
    Args:
        entries_by_crawler: Dict with key as crawler name, value as list of entries
    
    Returns:
        Dict with key as crawler name, value as number of saved entries
    """
    save_results = {}
    
    for crawler_name, entries in entries_by_crawler.items():
        if not entries:
            save_results[crawler_name] = 0
            continue
        
        try:
            num_inserted = insert_many_companies(entries)
            save_results[crawler_name] = num_inserted
            logger.info(f"Saved {num_inserted} entries from {crawler_name}")
        except Exception as e:
            logger.error(f"Error saving entries from {crawler_name}: {e}")
            save_results[crawler_name] = 0
    
    return save_results

def main():
    """Main function to run crawler."""
    available_crawlers = list(CRAWLERS.keys())
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command in available_crawlers:
            print(f"Running {command.capitalize()} crawler only...")
            results = run_crawlers([command])
        elif command == 'all':
            print("Running all available crawlers...")
            results = run_crawlers(available_crawlers)
        else:
            print(f"Usage: python main.py [{'|'.join(available_crawlers)}|all]")
            print("  techcrunch: Crawl TechCrunch only")
            print("  finsmes: Crawl Finsmes only")
            print("  all: Crawl both (default)")
            return
    else:
        print("Running both crawlers...")
        results = run_crawlers(available_crawlers)
    
    # Save results to database
    if results:
        save_results = save_entries_bulk(results)
        
        # Summary
        total_saved = sum(save_results.values())
        print(f"\n=== RESULTS SUMMARY ===")
        print(f"Total entries saved: {total_saved}")
        for crawler_name, saved_count in save_results.items():
            print(f"  {crawler_name}: {saved_count} entries")
    else:
        print("No results to save.")

if __name__ == "__main__":
    main() 