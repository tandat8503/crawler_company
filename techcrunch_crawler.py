import requests
from bs4 import BeautifulSoup
import re
import logging
from datetime import datetime, timedelta, date, timezone
from urllib.parse import urlparse

try:
    from thefuzz import fuzz
except ImportError:
    logging.warning('[WARNING] thefuzz is not installed. Please run: pip install thefuzz')
    fuzz = None

import config
from deduplication import (
    normalize_company_name, load_existing_entries, normalize_date
)
from search_utils import (
    find_company_website, find_company_linkedin, verify_company_info
)
from llm_utils import (
    extract_company_name_and_raised_date_llm, is_funding_article_llm, 
    extract_company_info_llm, normalize_domain, company_name_matches_domain,
    llm_prompt, safe_parse_json, extract_funding_info_llm,
    extract_funding_amount_llm, extract_funding_round_type_llm,
    validate_company_name_llm, extract_multiple_companies_llm,
    has_funding_keywords, extract_candidate_paragraphs,
    is_valid_url, normalize_company_name_for_search
)
from utils.logger import logger
from utils.retry import fetch_with_retry
from utils.data_normalizer import validate_and_normalize_entry, extract_funding_info_from_text
from db import insert_company, get_all_companies, insert_many_companies

TECHCRUNCH_URL = 'https://techcrunch.com/category/startups/'
HEADERS = config.HEADERS

def normalize_name(name):
    """Normalize name for matching"""
    return re.sub(r'[^a-z0-9]', '', name.lower())

def extract_domain_slug(url):
    """Extract domain slug from URL"""
    parsed = urlparse(url)
    domain = parsed.netloc.replace('www.', '')
    slug = normalize_name(''.join(domain.split('.')))
    return slug

def get_domain_root(url):
    """Get domain root from URL"""
    try:
        parsed = urlparse(url)
        host = parsed.netloc.replace('www.', '')
        parts = host.split('.')
        if len(parts) > 2:
            # Example: sub.example.ai -> example.ai
            return '.'.join(parts[-2:])
        elif len(parts) == 2:
            return '.'.join(parts)
        else:
            return parts[0] if parts else ''
    except Exception:
        return ''

def get_article_links_last_7_days(min_date=None, max_pages=5):
    """
    Crawl TechCrunch Startups page, get all articles in the date range [min_date, today]
    Updated to support new TechCrunch HTML structure
    """
    today = date.today()
    if min_date is None:
        min_date = today - timedelta(days=7)  # 7 days to get more articles
    
    links = []
    logger.info(f"Crawling TechCrunch from {min_date} to {today}")
    
    for page in range(1, max_pages + 1):
        page_url = f"{TECHCRUNCH_URL}page/{page}/" if page > 1 else TECHCRUNCH_URL
        try:
            logger.info(f"Fetching page {page}: {page_url}")
            resp = fetch_with_retry(page_url, headers=HEADERS)
            resp.raise_for_status()
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            all_older = True
            
            # Updated selectors based on actual TechCrunch HTML structure
            # Try multiple selectors to handle different page layouts
            cards = []
            
            # Method 1: New structure with li.wp-block-post
            cards = soup.find_all('li', class_='wp-block-post')
            if cards:
                logger.info(f"Page {page}: Found {len(cards)} articles with 'li.wp-block-post'")
            
            # Method 2: Fallback to div.wp-block-techcrunch-card
            if not cards:
                cards = soup.find_all('div', class_='wp-block-techcrunch-card')
                if cards:
                    logger.info(f"Page {page}: Found {len(cards)} articles with 'div.wp-block-techcrunch-card'")
            
            # Method 3: Generic article tags
            if not cards:
                cards = soup.find_all('article')
                if cards:
                    logger.info(f"Page {page}: Found {len(cards)} articles with 'article' tags")
            
            # Method 4: Any div with 'card' in class name
            if not cards:
                cards = soup.find_all('div', class_=lambda x: x and 'card' in x)
                if cards:
                    logger.info(f"Page {page}: Found {len(cards)} articles with 'card' in class")
            
            # Method 5: Any element with article-like structure
            if not cards:
                # Look for any element that might contain article links
                potential_cards = soup.find_all(['div', 'article', 'li'], class_=lambda x: x and any(word in str(x).lower() for word in ['post', 'article', 'card', 'item']))
                cards = potential_cards
                if cards:
                    logger.info(f"Page {page}: Found {len(cards)} potential articles with generic selectors")
            
            if not cards:
                logger.warning(f"Page {page}: No articles found with any selector")
                continue
            
            logger.info(f"Page {page}: Processing {len(cards)} articles")
            
            for i, card in enumerate(cards):
                # Find article link with multiple fallback methods
                a_tag = None
                
                # Method 1: Look for loop-card_title-link (from the image)
                title_link = card.find('a', class_='loop-card_title-link')
                if title_link:
                    a_tag = title_link
                    logger.debug(f"Card {i}: Found link with 'loop-card_title-link'")
                
                # Method 2: Look for h3 with loop-card_title class
                if not a_tag:
                    title_h3 = card.find('h3', class_='loop-card_title')
                    if title_h3:
                        a_tag = title_h3.find('a')
                        if a_tag:
                            logger.debug(f"Card {i}: Found link with 'h3.loop-card_title'")
                
                # Method 3: Look for h2 with title class
                if not a_tag:
                    title_h2 = card.find('h2', class_='wp-block-tc2023-post-card__title')
                    if title_h2:
                        a_tag = title_h2.find('a')
                        if a_tag:
                            logger.debug(f"Card {i}: Found link with 'h2.wp-block-tc2023-post-card__title'")
                
                # Method 4: Look for any h2 or h3 with a tag
                if not a_tag:
                    for heading in card.find_all(['h2', 'h3']):
                        a_tag = heading.find('a')
                        if a_tag:
                            logger.debug(f"Card {i}: Found link with '{heading.name}' tag")
                            break
                
                # Method 5: Look for any a tag with href containing article URL pattern
                if not a_tag:
                    a_tags = card.find_all('a', href=True)
                    for a in a_tags:
                        href = a.get('href', '')
                        # Look for article URLs (containing year or specific patterns)
                        if any(pattern in href for pattern in ['/202', '/article', '/post', 'techcrunch.com']):
                            a_tag = a
                            logger.debug(f"Card {i}: Found link with URL pattern: {href}")
                            break
                
                # Method 6: Take first a tag if nothing else found
                if not a_tag:
                    a_tags = card.find_all('a', href=True)
                    if a_tags:
                        a_tag = a_tags[0]
                        logger.debug(f"Card {i}: Using first a tag as fallback")
                
                if a_tag and a_tag.get('href'):
                    url = a_tag['href']
                    if not url.startswith('http'):
                        url = 'https://techcrunch.com' + url
                    
                    logger.info(f"Found URL: {url}")
                    
                    # Enhanced date parsing with multiple fallbacks
                    pub_date = today
                    date_found = False
                    
                    # Method 1: Look for time tag with datetime attribute
                    time_tag = card.find('time')
                    if time_tag and time_tag.has_attr('datetime'):
                        try:
                            pub_date_str = time_tag['datetime']
                            # Handle ISO 8601 format with Z or timezone offset
                            if 'Z' in pub_date_str:
                                pub_date_str = pub_date_str.replace('Z', '+00:00')
                            pub_date = datetime.fromisoformat(pub_date_str).date()
                            logger.info(f"Found date: {pub_date} from datetime: {time_tag['datetime']}")
                            date_found = True
                        except ValueError as e:
                            logger.warning(f"Error parsing ISO date: {e}")
                            # Fallback: try to parse just the date part
                            try:
                                date_part = pub_date_str.split('T')[0]
                                pub_date = datetime.strptime(date_part, '%Y-%m-%d').date()
                                logger.info(f"Found date (fallback): {pub_date} from date part: {date_part}")
                                date_found = True
                            except Exception as e2:
                                logger.warning(f"Error parsing date part: {e2}")
                    
                    # Method 2: Look for other date elements
                    if not date_found:
                        date_elements = card.find_all(['time', 'span', 'div'], class_=lambda x: x and any(word in str(x).lower() for word in ['date', 'time', 'published']))
                        for date_elem in date_elements:
                            try:
                                date_text = date_elem.get_text(strip=True)
                                # Try to parse various date formats
                                for fmt in ['%Y-%m-%d', '%B %d, %Y', '%d %B %Y', '%Y/%m/%d']:
                                    try:
                                        pub_date = datetime.strptime(date_text, fmt).date()
                                        logger.info(f"Found date: {pub_date} from text: {date_text}")
                                        date_found = True
                                        break
                                    except ValueError:
                                        continue
                                if date_found:
                                    break
                            except Exception as e:
                                logger.debug(f"Error parsing date element: {e}")
                    
                    if not date_found:
                        logger.info("No date found, using today's date")
                        pub_date = today
                    
                    # Check date range with more flexible logic
                    logger.info(f"Checking date range: {min_date} <= {pub_date} <= {today}")
                    if min_date <= pub_date <= today:
                        links.append((url, pub_date.isoformat()))
                        all_older = False
                        logger.info(f"Added article: {url} | {pub_date}")
                    else:
                        logger.info(f"Skipped article (out of date range): {url} | {pub_date}")
                else:
                    logger.warning(f"Card {i}: No main article link (a_tag) found in card")
                    # Debug: log card structure for first few cards
                    if i < 3:
                        logger.debug(f"Card {i} classes: {card.get('class', [])}")
                        logger.debug(f"Card {i} HTML: {str(card)[:200]}...")
            
            if all_older:
                logger.info(f"Page {page}: All articles are older than {min_date}, stopping")
                break
                
        except Exception as e:
            logger.error(f"[ERROR][TechCrunch] Page {page}: {e}")
            break
    
    logger.info(f"Total articles found: {len(links)}")
    return links

def extract_article_links_and_context(soup, company_name):
    """
    Extract all anchor tags (<a>) in the article, along with surrounding context
    Return a list of dicts: {url, anchor_text, context, domain, company_norm}
    """
    results = []
    company_norm = normalize_company_name(company_name)
    
    for a in soup.find_all('a', href=True):
        url = a['href']
        anchor_text = a.get_text(strip=True)
        
        # Get context: 1-2 sentences before/after anchor
        parent = a.parent
        context = ''
        if parent:
            text = parent.get_text(separator=' ', strip=True)
            idx = text.find(anchor_text)
            if idx != -1:
                before = text[:idx].strip().split('.')[-1]
                after = text[idx+len(anchor_text):].strip().split('.')[0]
                context = f"{before} [{anchor_text}] {after}".strip()
            else:
                context = text
        
        domain = urlparse(url).netloc.lower()
        results.append({
            'url': url,
            'anchor_text': anchor_text,
            'context': context,
            'domain': domain,
            'company_norm': company_norm
        })
    
    return results

def extract_best_links_from_anchors(links_context, company_name, top_n=3):
    """
    Return top N website and top N linkedin with highest scores
    """
    norm_company = normalize_name(company_name)
    website_candidates = []
    linkedin_candidates = []
    
    for link in links_context:
        url = link['url']
        domain = urlparse(url).netloc.lower()
        domain_slug = extract_domain_slug(url)
        score = fuzz.partial_ratio(norm_company, domain_slug) if fuzz else 0
        
        # Website: exclude linkedin, facebook, crunchbase...
        if not any(x in domain for x in ['linkedin.com', 'facebook.com', 'twitter.com', 'crunchbase.com', 'news.', '/news/']):
            website_candidates.append((url, score))
        
        # LinkedIn
        if 'linkedin.com/company' in url:
            linkedin_candidates.append((url, score))
    
    # Sort and get top N
    website_candidates = sorted(website_candidates, key=lambda x: x[1], reverse=True)[:top_n]
    linkedin_candidates = sorted(linkedin_candidates, key=lambda x: x[1], reverse=True)[:top_n]
    
    websites = [w for w, s in website_candidates]
    linkedins = [l for l, s in linkedin_candidates]
    
    return websites, linkedins

def extract_company_info(article_url):
    """
    Extract company name, website, and date from a TechCrunch article
    Optimized: extract company_name early for anchor matching
    """
    try:
        source = "TechCrunch"
        crawl_date = datetime.now(timezone.utc).date().isoformat()
        
        resp = fetch_with_retry(article_url, headers=HEADERS)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Get article content using multiple selectors
        article_text = ""
        content_div = None
        
        # Try multiple content selectors
        content_selectors = [
            'div.wp-block-post-content',
            'div.entry-content',
            'div.post-content', 
            'div.article-content',
            'div.article-body',
            'article .content',
            'div.content'
        ]
        
        for selector in content_selectors:
            content_div = soup.select_one(selector)
            if content_div:
                logger.debug(f"Found content with selector: {selector}")
                break
        
        # Fallback to generic article tag if specific divs not found
        if not content_div:
            content_div = soup.find('article')
            if content_div:
                logger.debug("Found content with generic 'article' tag")
        
        if content_div:
            paragraphs = content_div.find_all('p')
            article_text = " ".join(p.get_text() for p in paragraphs)
            logger.info(f"Content length: {len(article_text)} characters")
        else:
            logger.warning("Article content not found")
            return None

        # 1. Extract company_name early (IMPORTANT: for anchor matching)
        today = date.today()
        min_date_iso = (today - timedelta(days=7)).isoformat()
        max_date_iso = today.isoformat()
        
        temp_info = extract_company_name_and_raised_date_llm(article_text, min_date_iso, max_date_iso)
        company_name = temp_info.get('company_name', '').strip() if temp_info else ''
        
        if not company_name:
            logger.warning(f"[NO COMPANY NAME] {article_url}")
            return None

        website = ''
        linkedin = ''
        
        # 2. Prioritize getting link from anchor (now we have company_name)
        links_context = extract_article_links_and_context(soup, company_name)
        websites_from_anchors, linkedins_from_anchors = extract_best_links_from_anchors(links_context, company_name, top_n=3)
        website = websites_from_anchors[0] if websites_from_anchors else ''
        linkedin = linkedins_from_anchors[0] if linkedins_from_anchors else ''

        # 3. If not available, use Tavily search
        if not website and company_name:
            logger.info(f"Searching for website using Tavily for '{company_name}'...")
            website = find_company_website(company_name)
        
        if not linkedin and company_name:
            logger.info(f"Searching for LinkedIn using Tavily for '{company_name}'...")
            linkedin = find_company_linkedin(company_name)

        # Get article publication date
        date_tag = soup.find('time')
        if date_tag and date_tag.has_attr('datetime'):
            date = datetime.fromisoformat(date_tag['datetime'].replace('Z', '+00:00')).date().isoformat()
        else:
            date = datetime.now(timezone.utc).date().isoformat()

        return {
            'date': date,
            'company_name': company_name,
            'website': website,
            'linkedin': linkedin,
            'article_url': article_url,
            'source': source,
            'crawl_date': crawl_date,
            'websites_top3': websites_from_anchors,
            'linkedins_top3': linkedins_from_anchors
        }
    except Exception as e:
        logger.error(f"[ERROR] {article_url} | {e}")
        return None

def crawl_techcrunch():
    """
    Crawl TechCrunch articles and extract company information
    Optimized: use keyword check before calling LLM
    """
    today = date.today()
    min_date = today - timedelta(days=7)  # 7 days to get more articles
    article_links = get_article_links_last_7_days(min_date=min_date, max_pages=5)
    logger.info(f'Found {len(article_links)} TechCrunch articles.')
    
    # Load existing entries from database for deduplication
    existing_entries = load_existing_entries()
    processed_entries = []  # Collect all entries for bulk insert
    
    logger.info(f"Processing {len(article_links)} articles...")
    
    for i, (url, pub_date) in enumerate(article_links):
        logger.info(f"\n=== Processing Article {i+1}/{len(article_links)} ===")
        logger.info(f"URL: {url}")
        logger.info(f"Date: {pub_date}")
        
        source = "TechCrunch"
        try:
            resp = fetch_with_retry(url, headers=HEADERS)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            title_tag = soup.find('h1')
            title = title_tag.get_text(strip=True) if title_tag else ''
            logger.info(f"Title: {title}")
            
            # Get article content using multiple selectors
            article_text = ""
            content_div = None
            
            # Try multiple content selectors
            content_selectors = [
                'div.wp-block-post-content',
                'div.entry-content',
                'div.post-content', 
                'div.article-content',
                'div.article-body',
                'article .content',
                'div.content'
            ]
            
            for selector in content_selectors:
                content_div = soup.select_one(selector)
                if content_div:
                    logger.debug(f"Found content with selector: {selector}")
                    break
            
            # Fallback to generic article tag if specific divs not found
            if not content_div:
                content_div = soup.find('article')
                if content_div:
                    logger.debug("Found content with generic 'article' tag")
            
            if content_div:
                paragraphs = content_div.find_all('p')
                article_text = " ".join(p.get_text() for p in paragraphs)
                logger.info(f"Content length: {len(article_text)} chars")
            else:
                logger.warning(f"[SKIP][NO CONTENT] {url}")
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
    
    logger.info(f"\n=== TECHCRUNCH SUMMARY ===")
    logger.info(f"Total articles processed: {len(article_links)}")
    logger.info(f"Total entries collected: {len(processed_entries)}")
    
    return []

if __name__ == '__main__':
    logger.info("=== TechCrunch Crawler ===")
    entries = crawl_techcrunch()
    logger.info("Done. Check database for results.") 