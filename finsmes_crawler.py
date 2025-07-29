import requests
from bs4 import BeautifulSoup
import re
import logging
from datetime import datetime, timedelta, date, timezone
from urllib.parse import urlparse
import time

try:
    from thefuzz import fuzz
except ImportError:
    logging.warning('[WARNING] thefuzz is not installed. Please run: pip install thefuzz')
    fuzz = None

import config
from deduplication import (
    normalize_company_name, load_existing_entries
)
from search_utils import (
    find_company_website, find_company_linkedin, verify_company_info
)
from llm_utils import (
    extract_company_name_and_raised_date_llm, is_funding_article_llm, 
    extract_funding_info_llm, is_negative_news, extract_company_info_llm,
    extract_funding_amount_llm, extract_funding_round_type_llm,
    validate_company_name_llm, extract_multiple_companies_llm,
    has_funding_keywords, extract_candidate_paragraphs
)
from utils.logger import logger
from utils.retry import fetch_with_retry
from utils.data_normalizer import validate_and_normalize_entry, extract_funding_info_from_text
from db import insert_company, get_all_companies, insert_many_companies

FINSMES_URL = 'https://www.finsmes.com/category/usa/'
HEADERS = config.HEADERS

def get_domain_root(url):
    """Extract domain root from URL, handling special TLDs"""
    try:
        parsed = urlparse(url)
        host = parsed.netloc.replace('www.', '')
        parts = host.split('.')
        if len(parts) >= 2:
            return f"{parts[-2]}.{parts[-1]}"
        return host
    except Exception:
        return ""

def crawl_finsmes_usa(max_pages=5):
    """
    Crawl Finsmes USA articles.
    """
    articles = []
    for page in range(1, max_pages+1):
        url = f"{FINSMES_URL}page/{page}/" if page > 1 else FINSMES_URL
        try:
            logger.info(f"Fetching page {page}: {url}")
            resp = fetch_with_retry(url, headers=HEADERS)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.find_all("div", class_="td-module-meta-info")
            logger.info(f"Page {page}: Found {len(cards)} cards with 'td-module-meta-info'")
            
            for meta in cards:
                h3 = meta.find("h3", class_="entry-title")
                a = h3.find("a") if h3 else None
                article_url = a["href"] if a else None
                title = a.get_text(strip=True) if a else ""
                date_div = meta.find("div", class_="td-editor-date")
                pub_date = date_div.get_text(strip=True) if date_div else ""
                
                if article_url:
                    articles.append({
                        "url": article_url,
                        "title": title,
                        "pub_date": pub_date
                    })
                    logger.info(f"Found article: {title} | {article_url} | {pub_date}")
            
            time.sleep(1)  # Be respectful to the server
        except Exception as e:
            logger.error(f"[ERROR][Finsmes] Page {page}: {e}")
    
    logger.info(f"Total Finsmes articles found: {len(articles)}")
    return articles

def extract_finsmes_article_detail(article_url):
    """
    Extract article detail from Finsmes.
    """
    try:
        resp = fetch_with_retry(article_url, headers=HEADERS)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Try multiple content selectors for Finsmes
        content_div = None
        content_selectors = [
            'div.td-post-content',
            'div.vc_column_container',
            'div.entry-content',
            'div.post-content',
            'article .content'
        ]
        
        for selector in content_selectors:
            content_div = soup.select_one(selector)
            if content_div:
                logger.debug(f"Found content with selector: {selector}")
                break
        
        # Fallback to generic article tag if specific divs not found
        if not content_div:
            content_div = soup.find("article")
            if content_div:
                logger.debug("Found content with generic 'article' tag")
        
        article_text = ""
        if content_div:
            paragraphs = content_div.find_all("p")
            article_text = " ".join(p.get_text() for p in paragraphs)
            logger.info(f"Content length: {len(article_text)} chars")
        
        return soup, article_text
    except Exception as e:
        logger.error(f"[ERROR][Finsmes Detail] {article_url}: {e}")
        return None, ""

def extract_possible_company_website(soup, company_name):
    """
    Extract possible company website from article links.
    """
    norm_name = company_name.lower().replace(' ', '')
    for a in soup.find_all('a', href=True):
        text = a.get_text(strip=True)
        href = a['href']
        if norm_name and norm_name in text.lower().replace(' ', ''):
            if not any(x in href for x in ['techcrunch.com', 'linkedin.com', 'facebook.com', 'twitter.com', 'crunchbase.com', 'news.', '/news/']):
                return href
    return ""

def crawl_finsmes():
    """
    Crawl Finsmes articles and extract company information.
    """
    today = date.today()
    min_date = today - timedelta(days=7)  # 7 days to get more articles
    finsmes_articles = crawl_finsmes_usa(max_pages=5)
    logger.info(f'Found {len(finsmes_articles)} Finsmes articles.')
    
    # Load existing entries from database for deduplication
    existing_entries = load_existing_entries()
    processed_entries = []  # Collect all entries for bulk insert
    
    logger.info(f"Processing {len(finsmes_articles)} articles...")
    
    for i, article in enumerate(finsmes_articles):
        url = article['url']
        pub_date = article['pub_date']
        title = article['title']
        
        logger.info(f"\n=== Processing Finsmes Article {i+1}/{len(finsmes_articles)} ===")
        logger.info(f"URL: {url}")
        logger.info(f"Title: {title}")
        logger.info(f"Date: {pub_date}")
        
        source = "Finsmes"
        try:
            soup, article_text = extract_finsmes_article_detail(url)
            if not article_text:
                logger.warning(f"[SKIP][NO CONTENT] {url}")
                continue
            
            if len(article_text) < 300:
                logger.info("[SKIP] Skipping article due to insufficient content.")
                continue
            
            # Check funding article (optimized: keyword check first)
            logger.info("Checking if funding article...")
            if not is_funding_article_llm(article_text):
                logger.info(f"[SKIP][NOT FUNDING] Title: {title} | Date: {pub_date} | URL: {url}")
                continue
            
            logger.info("✅ Article is funding-related")
            
            # Extract company information using enhanced LLM functions
            logger.info("Extracting company info...")
            
            # Try multiple extraction methods
            company_infos = []
            
            # Method 1: Standard extraction
            info = extract_company_name_and_raised_date_llm(article_text, min_date.isoformat(), today.isoformat())
            if info:
                company_infos.append(info)
            
            # Method 2: Enhanced extraction with funding info
            funding_info = extract_funding_info_llm(article_text)
            if funding_info:
                company_infos.append(funding_info)
            
            # Method 3: Multiple companies extraction
            multiple_companies = extract_multiple_companies_llm(article_text)
            if multiple_companies and multiple_companies.get('companies'):
                for company in multiple_companies['companies']:
                    if company.get('role') == 'startup':
                        company_infos.append({
                            'company_name': company.get('name', ''),
                            'raised_date': pub_date,
                            'amount': company.get('funding_amount', ''),
                            'round_type': company.get('round_type', '')
                        })
            
            # If no companies found, try basic extraction
            if not company_infos:
                logger.warning("No company info found, trying basic extraction...")
                # Use the first method as fallback
                info = extract_company_name_and_raised_date_llm(article_text, min_date.isoformat(), today.isoformat())
                if info:
                    company_infos = [info]
            
            logger.info(f"Found {len(company_infos)} company info(s)")
            
            for j, company_info in enumerate(company_infos):
                logger.info(f"Processing company info {j+1}/{len(company_infos)}")
                
                company_name = (company_info.get('company_name') or '').strip()
                raised_date = (company_info.get('raised_date') or '').strip() or pub_date
                amount = (company_info.get('amount') or '').strip()
                
                # Validate company name
                if company_name:
                    validation = validate_company_name_llm(company_name, article_text)
                    if validation and not validation.get('is_valid', True):
                        corrected_name = validation.get('corrected_name', '')
                        if corrected_name:
                            company_name = corrected_name
                            logger.info(f"Corrected company name: {company_name}")
                
                logger.info(f"Company: {company_name}")
                logger.info(f"Raised date: {raised_date}")
                logger.info(f"Amount: {amount}")
                
                if not company_name:
                    logger.warning("No company name found, skipping...")
                    continue
                
                # Check for duplicates using article_url (database will handle this)
                if url in existing_entries:
                    logger.info(f"[SKIP][EXISTING DUPLICATE] {company_name} | {raised_date} | {url}")
                    continue
                
                # Search for website and LinkedIn using Tavily
                logger.info("Searching for website and LinkedIn using Tavily...")
                website = find_company_website(company_name)
                linkedin = find_company_linkedin(company_name)
                crawl_date = today.isoformat()
                
                logger.info(f"Website: {website}")
                logger.info(f"LinkedIn: {linkedin}")
                
                # Extract additional funding info from text
                funding_details = extract_funding_info_from_text(article_text)
                
                entry = {
                    'raised_date': raised_date,
                    'company_name': company_name,
                    'website': website,
                    'linkedin': linkedin,
                    'article_url': url,
                    'amount_raised': amount or funding_details.get('amount', ''),
                    'currency': funding_details.get('currency', 'USD'),
                    'funding_round': company_info.get('round_type', '') or funding_details.get('round_type', ''),
                    'crawl_date': crawl_date,
                    'source': source
                }
                
                # Normalize the entry before adding to processed list
                normalized_entry = validate_and_normalize_entry(entry)
                
                # Add to processed entries for bulk insert
                processed_entries.append(normalized_entry)
                logger.info(f"✅ [COLLECTED] {company_name} | {raised_date} | {url}")
                logger.info(f"   Amount: {normalized_entry.get('amount_raised', '')} {normalized_entry.get('currency', 'USD')}")
                logger.info(f"   Round: {normalized_entry.get('funding_round', '')}")
                logger.info(f"   Website: {website}")
                logger.info(f"   LinkedIn: {linkedin}")
                
        except Exception as e:
            logger.error(f"[ERROR] {url} | {e}")
    
    # Bulk insert all processed entries
    if processed_entries:
        try:
            num_inserted = insert_many_companies(processed_entries)
            logger.info(f"✅ [BULK INSERT] Successfully processed {len(processed_entries)} entries, {num_inserted} new rows added to DB.")
        except Exception as e:
            logger.error(f"Error in bulk insert: {e}")
            # Fallback to individual inserts
            logger.info("Falling back to individual inserts...")
            for entry in processed_entries:
                try:
                    insert_company(entry)
                except Exception as e2:
                    logger.error(f"Error inserting individual entry: {e2}")
    else:
        logger.info("No entries to insert.")
    
    logger.info(f"\n=== FINSMES SUMMARY ===")
    logger.info(f"Total articles processed: {len(finsmes_articles)}")
    logger.info(f"Total entries collected: {len(processed_entries)}")
    
    return []

if __name__ == '__main__':
    logger.info("=== Finsmes Crawler ===")
    entries = crawl_finsmes()
    logger.info("Done. Check database for results.") 