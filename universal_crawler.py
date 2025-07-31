#!/usr/bin/env python3
"""
Universal Crawler Engine - Optimized Version
Có thể crawl bất kỳ URL nào từ các sources được hỗ trợ với tối ưu hóa hiệu suất
"""

import asyncio
import json
from typing import Dict, Any, List
from datetime import datetime
from urllib.parse import urlparse
import aiohttp
import ssl
from bs4 import BeautifulSoup
import re

from content_extractor import extract_main_content
from llm_utils import extract_structured_data_llm
from search_utils import find_company_website, find_company_linkedin
from utils.logger import logger
from utils.data_normalizer import normalize_currency_amount, normalize_funding_round, normalize_company_name
from db import insert_many_companies

# --- Helper function to extract published date from HTML and URL ---
def extract_published_date_from_html(html: str, url: str) -> str | None:
    """
    Extract published date from HTML content or URL using common patterns.
    Returns date in YYYY-MM-DD format or None if not found.
    """
    try:
        soup = BeautifulSoup(html, 'html.parser')
        # 1. Try <meta property="article:published_time">
        meta_time = soup.find('meta', attrs={'property': 'article:published_time'})
        if meta_time and meta_time.get('content'):
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', meta_time['content'])
            if date_match:
                return date_match.group(1)
        # 2. Try <time datetime="...">
        time_tag = soup.find('time')
        if time_tag and time_tag.has_attr('datetime'):
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', time_tag['datetime'])
            if date_match:
                return date_match.group(1)
        # 3. Try <meta name="pubdate"> or <meta name="date">
        for meta_name in ['pubdate', 'date']:
            meta = soup.find('meta', attrs={'name': meta_name})
            if meta and meta.get('content'):
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', meta['content'])
                if date_match:
                    return date_match.group(1)
        # 4. Try to extract from URL (e.g., /2023/12/31/)
        url_date_match = re.search(r'/(\d{4})/(\d{2})/(\d{2})/', url)
        if url_date_match:
            year, month, day = url_date_match.groups()
            return f"{year}-{month}-{day}"
    except Exception as e:
        logger.warning(f"Error extracting published date from HTML: {e}")
    return None

class UniversalCrawler:
    def __init__(self):
        self.supported_sources = self._load_supported_sources()
        logger.info(f"Initialized UniversalCrawler with {len(self.supported_sources)} supported sources")

    def _load_supported_sources(self) -> Dict[str, Dict]:
        """Load supported sources from config file."""
        try:
            with open('config/sources.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning("sources.json not found, using default sources")
            return {
            'techcrunch': {
                'name': 'TechCrunch',
                    'domains': ['techcrunch.com', 'stories.techcrunch.com']
            },
            'finsmes': {
                'name': 'Finsmes',
                    'domains': ['finsmes.com']
                },
                'crunchbase': {
                    'name': 'Crunchbase',
                    'domains': ['crunchbase.com', 'news.crunchbase.com']
                }
            }

    def detect_source(self, url: str) -> str | None:
        """Detect the source of the URL with enhanced domain matching."""
        try:
            domain = urlparse(url).netloc.lower().replace('www.', '')
            
            # First, try exact domain matching
            for source, config in self.supported_sources.items():
                for base_domain in config['domains']:
                    if domain == base_domain:
                        logger.info(f"Detected supported source: {config['name']} from URL: {url}")
                        return source
            
            # Then, try subdomain matching
            for source, config in self.supported_sources.items():
                for base_domain in config['domains']:
                    if domain.endswith('.' + base_domain):
                        logger.info(f"Detected supported source (subdomain): {config['name']} from URL: {url}")
                        return source
            
            # Finally, try partial domain matching for unknown sources
            for source, config in self.supported_sources.items():
                for base_domain in config['domains']:
                    if base_domain in domain:
                        logger.info(f"Detected potential source (partial match): {config['name']} from URL: {url}")
                        return source
            
            # If no match found, try to auto-detect based on domain patterns
            auto_detected = self._auto_detect_source(domain)
            if auto_detected:
                logger.info(f"Auto-detected source: {auto_detected} from URL: {url}")
                return auto_detected
            
            logger.warning(f"Unsupported source for URL: {url}")
            return None
        except Exception as e:
            logger.error(f"Error detecting source for {url}: {e}")
            return None
    
    def _auto_detect_source(self, domain: str) -> str | None:
        """Auto-detect source based on domain patterns and common news sites."""
        # Common news domain patterns
        news_patterns = {
            'tech': ['tech', 'startup', 'venture', 'innovation'],
            'business': ['business', 'finance', 'market', 'economy'],
            'news': ['news', 'media', 'press', 'journal'],
            'ai': ['ai', 'artificial', 'intelligence', 'machine'],
            'fintech': ['fintech', 'fin', 'banking', 'payment']
        }
        
        # Check if domain contains news-related keywords
        domain_lower = domain.lower()
        for category, keywords in news_patterns.items():
            for keyword in keywords:
                if keyword in domain_lower:
                    # Create a generic source name
                    return f"auto_{category}"
        
        return None

    async def crawl_single_url(self, url: str) -> Dict[str, Any]:
        """Crawl a single URL and extract funding information."""
        try:
            logger.info(f"🔄 Starting crawl for: {url}")
            
            # Validate URL
            if not url or not url.startswith(('http://', 'https://')):
                return {'success': False, 'error': 'Invalid URL format', 'url': url}
            
            # Detect source
            source = self.detect_source(url)
            if not source:
                return {'success': False, 'error': 'Unsupported source', 'url': url}

            # Extract main content
            article_text = await asyncio.to_thread(extract_main_content, url)
            if not article_text or len(article_text.strip()) < 200:
                return {'success': False, 'error': 'Could not extract sufficient article content', 'url': url}

            # --- NEW: Fetch full HTML for date extraction ---
            import requests
            try:
                resp = await asyncio.to_thread(requests.get, url, timeout=10)
                html = resp.text if resp.status_code == 200 else ''
            except Exception as e:
                logger.warning(f"Could not fetch HTML for date extraction: {e}")
                html = ''

            # Extract structured data using LLM
            extracted_data = await asyncio.to_thread(extract_structured_data_llm, article_text)
            if not extracted_data:
                return {'success': False, 'error': 'LLM failed to extract structured data', 'url': url}

            # Extract company name and validate
            company_name = extracted_data.get('company_name')
            if not company_name:
                return {'success': False, 'error': 'No company name found in article', 'url': url}

            # Normalize company name
            company_name = normalize_company_name(company_name)

            # Extract and normalize amount raised
            amount_raised = extracted_data.get('amount_raised')
            if amount_raised:
                normalized_amount, _ = normalize_currency_amount(str(amount_raised))
                amount_raised = normalized_amount

            # Normalize funding round
            funding_round = extracted_data.get('funding_round')
            if funding_round:
                funding_round = normalize_funding_round(funding_round)

            # Find company website and LinkedIn
            website = None
            linkedin = None
            try:
                website = await asyncio.to_thread(find_company_website, company_name)
                linkedin = await asyncio.to_thread(find_company_linkedin, company_name)
            except Exception as e:
                logger.warning(f"Error finding company links for {company_name}: {e}")
            
            # --- NEW: Fallback for raised_date ---
            raised_date = extracted_data.get('raised_date')
            if not raised_date and html:
                raised_date = extract_published_date_from_html(html, url)
            
            # Prepare result
            result = {
                'success': True,
                'url': url,
                'article_url': url,
                'raised_date': raised_date,
                'company_name': company_name,
                'industry': extracted_data.get('industry'),
                'ceo_name': extracted_data.get('ceo_name'),
                'procurement_name': extracted_data.get('procurement_name'),
                'purchasing_name': extracted_data.get('purchasing_name'),
                'manager_name': extracted_data.get('manager_name'),
                'amount_raised': amount_raised,
                'funding_round': funding_round,
                'source': self.supported_sources[source]['name'],
                'website': website,
                'linkedin': linkedin
            }

            logger.info(f"✅ Successfully extracted data for {company_name}")
            return result
            
        except Exception as e:
            logger.error(f"Error crawling {url}: {e}")
            return {'success': False, 'error': str(e), 'url': url}

    async def crawl_list_page_and_extract(self, list_page_url: str, max_articles: int = 20, 
                                        num_workers: int = 5, save_to_db: bool = True,
                                        start_date: str = None, end_date: str = None) -> List[Dict[str, Any]]:
        """Crawl a list page and extract funding information from articles."""
        try:
            logger.info(f"🔄 Starting list page crawl: {list_page_url}")
            
            # Import trực tiếp để tránh recursive call
            from list_page_crawler import crawl_list_page_async as extract_articles
            
            # Extract article links
            funding_articles = await extract_articles(list_page_url, max_articles, start_date, end_date)
            
            if not funding_articles:
                logger.warning("No funding articles found on the list page")
                return []

            logger.info(f"Found {len(funding_articles)} funding articles to process")

            # Process articles with workers
            results = await self._process_with_workers(funding_articles, num_workers)
            
            # Save to database if requested
            if save_to_db and results:
                await self.save_results_to_database(results)

            logger.info(f"✅ List page crawl completed. Processed {len(results)} articles")
            return results

        except Exception as e:
            logger.error(f"Error in list page crawl: {e}")
            return []

    async def _process_with_workers(self, articles: List[Dict[str, str]], num_workers: int = 5) -> List[Dict[str, Any]]:
        """Process articles using worker coroutines."""
        queue = asyncio.Queue()
        results = []

        # Add articles to queue
        for article in articles:
            await queue.put(article)

        # Create worker tasks
        tasks = [asyncio.create_task(self._worker(f'worker-{i}', queue, results)) 
                for i in range(num_workers)]

        # Wait for all tasks to complete
        await queue.join()
        
        # Cancel workers
        for task in tasks:
            task.cancel()
        
        await asyncio.gather(*tasks, return_exceptions=True)
        
        return results

    async def _worker(self, name: str, queue: asyncio.Queue, results: List[Dict[str, Any]]):
        """Worker coroutine to process articles from queue."""
        try:
            while True:
                try:
                    article = await asyncio.wait_for(queue.get(), timeout=5.0)
                    result = await self.crawl_single_url(article['url'])
                    if result.get('success'):
                        results.append(result)
                    queue.task_done()
                except asyncio.TimeoutError:
                    logger.info(f"{name} worker timeout, stopping")
                    break
                except Exception as e:
                    logger.error(f"Error in worker {name}: {e}")
                    if 'article' in locals():
                        queue.task_done()
        except Exception as e:
            logger.error(f"Critical error in worker {name}: {e}")

    async def save_results_to_database(self, results: List[Dict[str, Any]]) -> int:
        """Save processed results to database."""
        if not results:
            return 0
        
        try:
            db_entries = []
            for result in results:
                if result.get('success'):
                    db_entry = {
                        'raised_date': result.get('raised_date'),
                        'company_name': result.get('company_name'),
                        'industry': result.get('industry'),
                        'ceo_name': result.get('ceo_name'),
                        'procurement_name': result.get('procurement_name'),
                        'purchasing_name': result.get('purchasing_name'),
                        'manager_name': result.get('manager_name'),
                        'amount_raised': str(result.get('amount_raised')) if result.get('amount_raised') is not None else None,
                        'funding_round': result.get('funding_round'),
                        'source': result.get('source'),
                        'website': result.get('website'),
                        'linkedin': result.get('linkedin'),
                        'article_url': result.get('article_url')
                    }
                    db_entries.append(db_entry)
            
            if db_entries:
                num_inserted = insert_many_companies(db_entries)
                logger.info(f"✅ Successfully saved {num_inserted} new entries to the database.")
                return num_inserted
            else:
                return 0
        except Exception as e:
            logger.error(f"Error saving results to database: {e}")
            return 0

# Module-level functions for easy access
async def crawl_url_async(url: str) -> Dict[str, Any]:
    """Async wrapper for crawling a single URL."""
    crawler = UniversalCrawler()
    return await crawler.crawl_single_url(url)

def crawl_url(url: str) -> Dict[str, Any]:
    """Sync wrapper for crawling a single URL."""
    return asyncio.run(crawl_url_async(url))

async def crawl_urls_async(urls: List[str]) -> List[Dict[str, Any]]:
    """Async wrapper for crawling multiple URLs."""
    crawler = UniversalCrawler()
    results = []
    for url in urls:
        result = await crawler.crawl_single_url(url)
        results.append(result)
    return results

def crawl_urls(urls: List[str]) -> List[Dict[str, Any]]:
    """Sync wrapper for crawling multiple URLs."""
    return asyncio.run(crawl_urls_async(urls))

async def crawl_list_page_async(list_page_url: str, max_articles: int = 20, 
                                num_workers: int = 5, save_to_db: bool = True,
                                start_date: str = None, end_date: str = None) -> List[Dict[str, Any]]:
    """Async wrapper for crawling a list page."""
    crawler = UniversalCrawler()
    return await crawler.crawl_list_page_and_extract(
        list_page_url, max_articles, num_workers, save_to_db, start_date, end_date
    )

def crawl_list_page(list_page_url: str, max_articles: int = 20, 
                   num_workers: int = 5, save_to_db: bool = True,
                   start_date: str = None, end_date: str = None) -> List[Dict[str, Any]]:
    """Sync wrapper for crawling a list page."""
    return asyncio.run(crawl_list_page_async(
        list_page_url, max_articles, num_workers, save_to_db, start_date, end_date
    ))

def get_supported_sources() -> Dict[str, str]:
    """Get list of supported sources."""
    try:
        with open('config/sources.json', 'r', encoding='utf-8') as f:
            sources = json.load(f)
            return {source: config['name'] for source, config in sources.items()}
    except FileNotFoundError:
        return {
            'techcrunch': 'TechCrunch',
            'finsmes': 'Finsmes',
            'crunchbase': 'Crunchbase'
        }

# Global instance for convenience
universal_crawler = UniversalCrawler()