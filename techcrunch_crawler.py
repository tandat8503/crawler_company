import requests
from bs4 import BeautifulSoup
import csv
import re
import logging
from datetime import datetime, timedelta, date, timezone
from urllib.parse import urlparse

try:
    from thefuzz import fuzz
except ImportError:
    print('[WARNING] thefuzz is not installed. Please run: pip install thefuzz')
    fuzz = None

import config
from deduplication import (
    normalize_company_name, load_existing_entries, normalize_date
)
from search_utils import (
    search_google_website, search_google_linkedin, google_search_variants,
    multi_threshold_fuzzy_match, resolve_final_links_with_llm
)
from llm_utils import (
    extract_company_name_and_raised_date_llm, is_funding_article_llm, 
    extract_company_info_llm, normalize_domain, company_name_matches_domain,
    llm_prompt, safe_parse_json
)

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def normalize_name(name):
    return re.sub(r'[^a-z0-9]', '', name.lower())

def extract_domain_slug(url):
    parsed = urlparse(url)
    domain = parsed.netloc.replace('www.', '')
    # Join all domain parts, remove punctuation, lowercase
    slug = normalize_name(''.join(domain.split('.')))
    return slug

# Add get_domain_root function
def get_domain_root(url):
    try:
        parsed = urlparse(url)
        host = parsed.netloc.replace('www.', '')
        parts = host.split('.')
        if len(parts) >= 2:
            return f"{parts[-2]}.{parts[-1]}"
        return host
    except Exception:
        return ""

CSV_FILE = config.CSV_FILE
TECHCRUNCH_URL = 'https://techcrunch.com/category/startups/'
HEADERS = config.HEADERS

def get_article_links_last_7_days(min_date=None, max_pages=5):
    """
    Crawl TechCrunch Startups page, get all articles in the date range [min_date, today], stop when all articles on the page are older than min_date.
    Updated to support new TechCrunch HTML structure (2023+)
    """
    today = date.today()
    if min_date is None:
        min_date = today - timedelta(days=7)  # Increase to 7 days to get more articles
    links = []
    for page in range(1, max_pages + 1):
        page_url = f"https://techcrunch.com/category/startups/page/{page}/"
        try:
            logger.info(f"Fetching page {page}: {page_url}")
            resp = requests.get(page_url, headers=HEADERS, timeout=10)
            logger.info(f"Page {page} status: {resp.status_code}")
            soup = BeautifulSoup(resp.text, 'html.parser')
            all_older = True
            
            # New selector: article.wp-block-tc2023-post-card
            cards = soup.find_all('article', class_='wp-block-tc2023-post-card')
            logger.info(f"Page {page}: Found {len(cards)} articles with 'wp-block-tc2023-post-card'")
            
            # Fallbacks if new selector doesn't work
            if not cards:
                cards = soup.find_all('div', class_='wp-block-techcrunch-card')
                logger.info(f"Page {page}: Found {len(cards)} cards with 'wp-block-techcrunch-card' (fallback)")
            
            if not cards:
                cards = soup.find_all('article')
                logger.info(f"Page {page}: Found {len(cards)} articles (fallback)")
            
            if not cards:
                cards = soup.find_all('div', class_=lambda x: x and 'card' in x)
                logger.info(f"Page {page}: Found {len(cards)} divs with 'card' in class (fallback)")
            
            for card in cards:
                # New selector for link: h2.wp-block-tc2023-post-card__title > a
                title_h2 = card.find('h2', class_='wp-block-tc2023-post-card__title')
                a_tag = title_h2.find('a') if title_h2 else None
                
                if not a_tag:
                    # Fallback to old selector
                    content = card.find('div', class_='wp-block-techcrunch-card__content')
                    if not content:
                        content = card.find('div', class_=lambda x: x and 'content' in x)
                    if not content:
                        content = card  # Use card directly if no content found
                    
                    if content:
                        a_tag = content.find('a')
                
                if a_tag:
                    url = a_tag['href']
                    logger.info(f"Found URL: {url}")
                    
                    # New selector for time
                    time_tag = card.find('time')
                    
                    if time_tag and time_tag.has_attr('datetime'):
                        try:
                            pub_date = datetime.fromisoformat(time_tag['datetime'].replace('Z', '+00:00')).date()
                            logger.info(f"Found date: {pub_date} from datetime: {time_tag['datetime']}")
                        except Exception as e:
                            logger.warning(f"Error parsing date: {e}")
                            pub_date = today
                    else:
                        logger.info("No time tag found, using today's date")
                        pub_date = today
                    
                    logger.info(f"Checking date range: {min_date} <= {pub_date} <= {today}")
                    if min_date <= pub_date <= today:
                        links.append((url, pub_date.isoformat()))
                        all_older = False
                        logger.info(f"Added article: {url} | {pub_date}")
                    else:
                        logger.info(f"Skipped article (out of date range): {url} | {pub_date}")
                else:
                    logger.warning("No main article link (a_tag) found in card")
            
            if all_older:
                logger.info(f"Page {page}: All articles are older than {min_date}, stopping")
                break
            
            # Debug: find all potential article links
            all_links = soup.find_all('a', href=True)
            potential_articles = []
            for link in all_links:
                href = link['href']
                if '/2025/' in href or '/2024/' in href:
                    potential_articles.append(href)
            
            logger.info(f"Page {page}: Found {len(potential_articles)} potential article links")
            if potential_articles:
                for i, link in enumerate(potential_articles[:3]):
                    logger.info(f"  Potential article {i+1}: {link}")
                    
        except Exception as e:
            logger.error(f"[ERROR][TechCrunch] Page {page}: {e}")
            break
    
    logger.info(f"Total articles found: {len(links)}")
    return links

def extract_article_links_and_context(soup, company_name):
    """
    Extract all anchor tags (<a>) in the article, along with surrounding context (1-2 sentences before/after anchor).
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
    Return top N website and top N linkedin with highest scores.
    """
    norm_company = normalize_name(company_name)
    website_candidates = []
    linkedin_candidates = []
    
    for link in links_context:
        url = link['url']
        domain = urlparse(url).netloc.lower()
        domain_slug = extract_domain_slug(url)
        score = fuzz.partial_ratio(norm_company, domain_slug)
        
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
    Extract company name, website, and date from a TechCrunch article.
    Optimized: extract company_name early for anchor matching
    """
    try:
        source = "TechCrunch"
        crawl_date = datetime.now(timezone.utc).date().isoformat()
        
        resp = requests.get(article_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Get article content
        article_body = soup.find('div', class_='entry-content')
        article_text = ""
        if article_body:
            paragraphs = article_body.find_all('p')
            article_text = " ".join(p.get_text() for p in paragraphs)

        # 1. Extract company_name early (IMPORTANT: for anchor matching)
        temp_info = extract_company_name_and_raised_date_llm(article_text, (date.today() - timedelta(days=3)).isoformat(), date.today().isoformat())
        company_name = temp_info.get('company_name', '').strip() if temp_info else ''
        
        if not company_name:
            logger.warning(f"[NO COMPANY NAME] {article_url}")
            return None

        website = ''
        linkedin = ''
        llm_guesses = None
        llm_linkedin_guess = None
        
        # 2. Prioritize getting link from anchor (now we have company_name)
        links_context = extract_article_links_and_context(soup, company_name)
        websites_from_anchors, linkedins_from_anchors = extract_best_links_from_anchors(links_context, company_name, top_n=3)
        website = websites_from_anchors[0] if websites_from_anchors else ''
        linkedin = linkedins_from_anchors[0] if linkedins_from_anchors else ''

        # 3. If not available, use LLM with new prompt
        result_from_llm = None
        if not website or not linkedin:
            result_from_llm = extract_company_info_llm(article_text, links_context)
            if result_from_llm:
                # Update company_name if LLM provides
                llm_company_name = result_from_llm.get('company_name', '').strip()
                if llm_company_name and not company_name:
                    company_name = llm_company_name
                
                # Get LLM guesses
                llm_guesses = result_from_llm.get('website_guesses', [])
                llm_linkedin_guess = result_from_llm.get('linkedin_guess', '')
                
                if not website:
                    website = result_from_llm.get('website', '').strip()
                    # If website is still empty, try to get from website_guesses
                    if not website and llm_guesses and isinstance(llm_guesses, list):
                        website = llm_guesses[0].strip() if llm_guesses[0] else ''
                
                if not linkedin:
                    linkedin = result_from_llm.get('linkedin', '').strip()
                    if not linkedin and llm_linkedin_guess:
                        linkedin = llm_linkedin_guess.strip()
                
                logger.info(f"[LLM][REASONING] {company_name} | confidence: {result_from_llm.get('confidence', '')} | reasoning: {result_from_llm.get('reasoning', '')}")
        
        # 4. If still not available, fallback Google with multiple query variations and LLM guesses
        if not website and company_name:
            # Use LLM guesses in search
            website = search_google_website(company_name, llm_guesses=llm_guesses)
            
            # If still not available, try with variants
            if not website:
                urls_from_google = google_search_variants(company_name, 'website', llm_guesses=llm_guesses)
                if urls_from_google:
                    # Create list of URLs with scores for LLM rerank
                    urls_with_scores = []
                    for url in urls_from_google:
                        domain_root = get_domain_root(url)
                        if domain_root:
                            score, _, _ = multi_threshold_fuzzy_match(company_name, domain_root)
                            urls_with_scores.append((url, score))
                    
                    if urls_with_scores:
                        website = resolve_final_links_with_llm(urls_with_scores, company_name, "website", top_n=3)
        
        if not linkedin and company_name:
            # Use LLM guess in search
            linkedin = search_google_linkedin(company_name, website=website, llm_guess=llm_linkedin_guess)
            
            # If still not available, try with variants
            if not linkedin:
                urls_from_google = google_search_variants(company_name, 'linkedin', llm_guesses=llm_linkedin_guess)
                if urls_from_google:
                    # Create list of URLs with scores for LLM rerank
                    urls_with_scores = []
                    for url in urls_from_google:
                        if "linkedin.com/company" in url:
                            slug = url.rstrip("/").split("/")[-1]
                            if slug:
                                score, _, _ = multi_threshold_fuzzy_match(company_name, slug)
                                urls_with_scores.append((url, score))
                    
                    if urls_with_scores:
                        linkedin = resolve_final_links_with_llm(urls_with_scores, company_name, "LinkedIn", top_n=3)

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

def save_to_csv(entries):
    """
    Save entries to CSV file.
    """
    if not entries:
        return
    
    with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        for entry in entries:
            writer.writerow([
                entry.get('raised_date', ''),
                entry.get('company_name', ''),
                entry.get('website', ''),
                entry.get('linkedin', ''),
                entry.get('article_url', ''),
                entry.get('source', ''),
                entry.get('crawl_date', '')
            ])

def crawl_techcrunch():
    """
    Crawl TechCrunch articles and extract company information.
    Optimized: use keyword check before calling LLM
    """
    today = date.today()
    min_date = today - timedelta(days=7)  # Increase to 7 days
    article_links = get_article_links_last_7_days(min_date=min_date, max_pages=5)
    logger.info(f'Found {len(article_links)} TechCrunch articles.')
    
    existing_entries = load_existing_entries(CSV_FILE)
    unique_entries = {}
    
    logger.info(f"Processing {len(article_links)} articles...")
    
    for i, (url, pub_date) in enumerate(article_links):
        logger.info(f"\n=== Processing Article {i+1}/{len(article_links)} ===")
        logger.info(f"URL: {url}")
        logger.info(f"Date: {pub_date}")
        
        source = "TechCrunch"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            title_tag = soup.find('h1')
            title = title_tag.get_text(strip=True) if title_tag else ''
            logger.info(f"Title: {title}")
            
            article_body = soup.find('div', class_='entry-content')
            article_text = ""
            if article_body:
                paragraphs = article_body.find_all('p')
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
            
            # Extract company information
            logger.info("Extracting company info...")
            info = extract_company_name_and_raised_date_llm(article_text, min_date.isoformat(), today.isoformat())
            if isinstance(info, list):
                infos = info
            else:
                infos = [info]
            
            logger.info(f"Found {len(infos)} company info(s)")
            
            for j, company_info in enumerate(infos):
                logger.info(f"Processing company info {j+1}/{len(infos)}")
                
                company_name = (company_info.get('company_name') or '').strip()
                raised_date = (company_info.get('raised_date') or '').strip() or pub_date
                amount = (company_info.get('amount') or '').strip()
                
                logger.info(f"Company: {company_name}")
                logger.info(f"Raised date: {raised_date}")
                logger.info(f"Amount: {amount}")
                
                key = (
                    normalize_company_name(company_name),
                    normalize_date(raised_date),
                    url
                )
                if key in existing_entries:
                    logger.info(f"[SKIP][EXISTING DUPLICATE] {company_name} | {raised_date} | {url}")
                    continue
                if key in unique_entries:
                    logger.info(f"[SKIP][NEW DUPLICATE] {company_name} | {raised_date} | {url}")
                    continue
                
                # Search for website and LinkedIn
                logger.info("Searching for website and LinkedIn...")
                website = search_google_website(company_name)
                linkedin = search_google_linkedin(company_name, website=website)
                crawl_date = today.isoformat()
                
                logger.info(f"Website: {website}")
                logger.info(f"LinkedIn: {linkedin}")
                
                entry = {
                    'raised_date': raised_date,
                    'company_name': company_name,
                    'website': website,
                    'linkedin': linkedin,
                    'article_url': url,
                    'source': source,
                    'crawl_date': crawl_date
                }
                unique_entries[key] = entry
                logger.info(f"✅ [ADD] {company_name} | {raised_date} | {url}")
                logger.info(f"   Amount: {amount}")
                logger.info(f"   Website: {website}")
                logger.info(f"   LinkedIn: {linkedin}")
                
        except Exception as e:
            logger.error(f"[ERROR] {url} | {e}")
    
    logger.info(f"\n=== SUMMARY ===")
    logger.info(f"Total articles processed: {len(article_links)}")
    logger.info(f"Total unique entries found: {len(unique_entries)}")
    
    for key, entry in unique_entries.items():
        logger.info(f"Entry: {entry['company_name']} | {entry['raised_date']} | {entry['website']}")
    
    return list(unique_entries.values())

if __name__ == '__main__':
    logger.info("=== TechCrunch Crawler ===")
    entries = crawl_techcrunch()
    if entries:
        save_to_csv(entries)
        logger.info(f'Saved {len(entries)} TechCrunch entries.')
    else:
        logger.info('No TechCrunch entries found.')
    logger.info("Done. Check companies.csv for results.") 