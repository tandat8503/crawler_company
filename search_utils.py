import requests
from bs4 import BeautifulSoup
import time
import random
import re
from urllib.parse import urlparse
from thefuzz import fuzz
import logging
from llm_utils import (
    normalize_domain, company_name_matches_domain, 
    verify_url_with_llm, normalize_company_name_for_search,
    safe_parse_json, llm_prompt, fetch_page_content
)
import config

# Setup logging
logger = logging.getLogger(__name__)

try:
    from tavily import TavilyClient
    tavily_client = TavilyClient(api_key=config.TAVILY_API_KEY)
except ImportError:
    print('[WARNING] tavily-python chưa được cài đặt. Hãy chạy: pip install tavily-python')
    tavily_client = None
except Exception as e:
    print(f'[WARNING] Tavily client error: {e}')
    tavily_client = None

def normalize_name(name):
    """Normalize name for fuzzy matching"""
    return re.sub(r'[^a-z0-9]', '', name.lower())

COMPANY_DOMAIN_WHITELIST = {
    "runetechnologies": {
        "website": "https://www.runetech.co/",
        "linkedin": "https://www.linkedin.com/company/runetech/"
    },
    # Add other companies if needed
}

def get_whitelisted_links(company_name):
    norm_name = normalize_name(company_name)
    return COMPANY_DOMAIN_WHITELIST.get(norm_name, {})

def exponential_backoff_retry(func, max_retries=3, base_delay=2):
    """Retry with exponential backoff"""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if '429' in str(e) or 'blocked' in str(e).lower():
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                logger.warning(f"Rate limited, retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
            else:
                raise e
    raise Exception(f"Failed after {max_retries} retries")

def safe_tavily_search(query, search_depth="basic", max_results=10, max_retries=3):
    """Tavily search safely with retry logic and exponential backoff"""
    def _search():
        results = []
        try:
            if not tavily_client:
                logger.error("Tavily client not available")
                return results
            
            response = tavily_client.search(
                query=query,
                search_depth=search_depth,
                max_results=max_results,
                include_answer=False,
                include_raw_content=False,
                include_images=False
            )
            
            if response and 'results' in response:
                for result in response['results']:
                    if 'url' in result:
                        results.append(result['url'])
                        sleep_time = random.uniform(1, 3)  # Tavily is faster than Google
                        logger.info(f"[SAFE SEARCH] Sleep {sleep_time:.1f}s after each Tavily result...")
                        time.sleep(sleep_time)
            
            return results
        except Exception as e:
            logger.error(f"[ERROR][SAFE TAVILY SEARCH] {query} | {e}")
            raise e
    
    return exponential_backoff_retry(_search, max_retries)

def get_domain_root(url):
    """Extract domain root from URL, handling special TLDs"""
    return normalize_domain(url)

def fetch_title(url):
    """Fetch page title"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        title = soup.find('title')
        return title.get_text(strip=True) if title else ''
    except Exception as e:
        logger.warning(f"Error fetching title for {url}: {e}")
        return ''

def fetch_page_content(url, max_chars=1000):
    """Fetch page content to verify"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Get text from body
        body = soup.find('body')
        if body:
            text = body.get_text(separator=' ', strip=True)
            return text[:max_chars] + '...' if len(text) > max_chars else text
        
        return ''
    except Exception as e:
        logger.warning(f"Error fetching content for {url}: {e}")
        return ''

def is_likely_homepage(url, company_name):
    """Check if URL is a homepage"""
    domain = get_domain_root(url)
    company_norm = normalize_name(company_name)
    domain_norm = normalize_name(domain)
    
    # Check if domain contains company name
    return company_norm in domain_norm or domain_norm in company_norm

def enhanced_company_name_normalization(company_name):
    """Enhanced company name normalization - remove unnecessary words"""
    if not company_name:
        return ""
    
    # Remove unnecessary words
    stop_words = [
        'inc', 'llc', 'ltd', 'corp', 'corporation', 'company', 'co',
        'group', 'solutions', 'technologies', 'tech', 'systems',
        'ventures', 'capital', 'partners', 'holdings', 'plc', 'sas', 'sa', 'pte',
        'international', 'global', 'worldwide', 'enterprises'
    ]
    
    words = company_name.lower().split()
    filtered_words = [w for w in words if w not in stop_words]
    
    return ' '.join(filtered_words).strip()

def multi_threshold_fuzzy_match(company_name, domain, thresholds=[80, 70, 60, 50]):
    """Fuzzy match with multiple thresholds"""
    company_norm = enhanced_company_name_normalization(company_name)
    domain_norm = normalize_name(domain)
    
    scores = {
        'ratio': fuzz.ratio(company_norm, domain_norm),
        'partial_ratio': fuzz.partial_ratio(company_norm, domain_norm),
        'token_set_ratio': fuzz.token_set_ratio(company_norm, domain_norm),
        'token_sort_ratio': fuzz.token_sort_ratio(company_norm, domain_norm)
    }
    
    # Return highest score and matching type
    max_score = max(scores.values())
    max_type = max(scores, key=scores.get)
    
    # Check each threshold
    for threshold in thresholds:
        if max_score >= threshold:
            return max_score, max_type, threshold
    
    return max_score, max_type, 0

def search_tavily_website(company_name, llm_guesses=None):
    """Search for company website with improved matching and LLM guesses using Tavily"""
    # Create queries with LLM guesses
    queries = []
    
    # Basic query
    base_query = f"{company_name} official website"
    queries.append(base_query)
    
    # Add queries with LLM guesses
    if llm_guesses and isinstance(llm_guesses, list):
        for guess in llm_guesses[:2]:  # Use only the first 2 guesses
            if guess and isinstance(guess, str):
                # Remove protocol if present
                clean_guess = guess.replace('https://', '').replace('http://', '').replace('www.', '')
                if clean_guess:
                    queries.append(f"{company_name} {clean_guess}")
                    queries.append(f"{company_name} site:{clean_guess}")
    
    # Add queries with main keywords
    main_word = company_name.lower().split()[0]
    if len(main_word) > 2:  # Use only words with length > 2
        queries.append(f"{main_word} official site")
        queries.append(f"{main_word} homepage")
    
    # Add domain-specific queries
    domain_queries = [
        f"{company_name} site:.ai",
        f"{company_name} site:.com", 
        f"{company_name} site:.io",
        f"{company_name} site:.co",
        f"{company_name} site:.tech"
    ]
    queries.extend(domain_queries)
    
    all_urls = []
    for query in queries[:8]:  # Limit to 8 queries for Tavily
        try:
            urls = safe_tavily_search(query, search_depth="basic", max_results=5, max_retries=2)
            all_urls.extend(urls)
            if urls:  # If results found, stop
                break
        except Exception as e:
            logger.warning(f"Query failed: {query} - {e}")
            continue
    
    if not all_urls:
        return ""
    
    # Normalize company name
    company_norm = enhanced_company_name_normalization(company_name)
    main_word = company_name.lower().split()[0]
    
    best_url = ''
    best_score = 0
    best_type = ''
    
    for url in all_urls:
        domain_root = get_domain_root(url)
        if not domain_root:
            continue
            
        # Calculate score with multiple thresholds
        score, match_type, threshold = multi_threshold_fuzzy_match(company_norm, domain_root)
        logger.info(f"[MATCH][WEBSITE] {company_name} vs {domain_root} | score: {score} | type: {match_type} | threshold: {threshold}")
        
        # Improved logic: prioritize high score or main word match
        if score >= 60 and score > best_score:
            best_score = score
            best_url = url
            best_type = match_type
        elif main_word in domain_root.lower() and best_score < 60:
            best_score = 60
            best_url = url
            best_type = 'main_word_match'
    
    # If a URL with a good score is found
    if best_score >= 50:
        # Verify with LLM with context
        page_content = fetch_page_content(best_url, max_chars=500)
        if verify_url_with_llm(best_url, company_name, "website", context=page_content):
            logger.info(f"[VERIFIED][WEBSITE] {company_name} -> {best_url} (score: {best_score}, type: {best_type})")
            return best_url
        else:
            logger.warning(f"[UNVERIFIED][WEBSITE] {company_name} -> {best_url} (score: {best_score}, type: {best_type})")
            return best_url
    
    # Fallback: check title if no candidate meets threshold
    for url in all_urls:
        title = fetch_title(url)
        if title and company_name.lower().replace(' ', '') in title.lower().replace(' ', ''):
            logger.info(f"[MATCH][WEBSITE][FALLBACK TITLE] {company_name} in title: {title}")
            return url
    
    return ""

def search_tavily_linkedin(company_name, website=None, llm_guess=None):
    """Search for company LinkedIn with improved matching and LLM guess using Tavily"""
    # Create queries with LLM guess
    queries = []
    
    # Basic query
    base_query = f"{company_name} LinkedIn company page"
    queries.append(base_query)
    
    # Add query with LLM guess
    if llm_guess and isinstance(llm_guess, str):
        # Extract slug from LinkedIn URL guess
        if 'linkedin.com/company/' in llm_guess:
            slug = llm_guess.split('/company/')[-1].rstrip('/')
            if slug:
                queries.append(f"{company_name} {slug}")
                queries.append(f"site:linkedin.com/company {slug}")
    
    # Add query with main keywords
    main_word = company_name.lower().split()[0]
    if len(main_word) > 2:
        queries.append(f"{main_word} site:linkedin.com/company")
    
    # Add LinkedIn-specific queries
    linkedin_queries = [
        f"{company_name} site:linkedin.com/company",
        f"{company_name} LinkedIn",
        f"{company_name} company LinkedIn"
    ]
    queries.extend(linkedin_queries)
    
    all_urls = []
    for query in queries[:5]:  # Limit to 5 queries for LinkedIn
        try:
            urls = safe_tavily_search(query, search_depth="basic", max_results=5, max_retries=2)
            all_urls.extend(urls)
            if urls:
                break
        except Exception as e:
            logger.warning(f"LinkedIn query failed: {query} - {e}")
            continue
    
    if not all_urls:
        return ""
    
    # Normalize company name
    norm_company = enhanced_company_name_normalization(company_name)
    best_url = ''
    best_score = 0
    best_type = ''
    
    for url in all_urls:
        if "linkedin.com/company" not in url:
            continue
            
        # Extract slug from LinkedIn URL
        slug = url.rstrip("/").split("/")[-1]
        if not slug:
            continue
            
        # Calculate score with multiple thresholds
        score, match_type, threshold = multi_threshold_fuzzy_match(norm_company, slug)
        logger.info(f"[MATCH][LINKEDIN] {company_name} vs {slug} | score: {score} | type: {match_type} | threshold: {threshold}")
        
        if score >= 50 and score > best_score:
            best_score = score
            best_url = url
            best_type = match_type
    
    if best_score >= 50:
        # Verify with LLM with context
        page_content = fetch_page_content(best_url, max_chars=500)
        if verify_url_with_llm(best_url, company_name, "LinkedIn", context=page_content):
            logger.info(f"[VERIFIED][LINKEDIN] {company_name} -> {best_url} (score: {best_score}, type: {best_type})")
            return best_url
        else:
            logger.warning(f"[UNVERIFIED][LINKEDIN] {company_name} -> {best_url} (score: {best_score}, type: {best_type})")
            return best_url
    
    logger.warning(f"[TAVILY][LINKEDIN][FAIL] {company_name} | No suitable LinkedIn found.")
    return ""

def tavily_search_variants(company_name, search_type, llm_guesses=None):
    """Search Tavily with multiple query variations and LLM guesses"""
    queries = []
    
    if search_type == 'website':
        queries = [
            f"{company_name} official site",
            f"{company_name} homepage",
            f"{company_name} {company_name.split()[-1]}",
            f"{company_name} site:.ai OR site:.com OR site:.io OR site:.energy OR site:.net OR site:.org OR site:.co OR site:.tech OR site:.app",
        ]
        
        # Add queries with LLM guesses
        if llm_guesses and isinstance(llm_guesses, list):
            for guess in llm_guesses[:2]:
                if guess and isinstance(guess, str):
                    clean_guess = guess.replace('https://', '').replace('http://', '').replace('www.', '')
                    if clean_guess:
                        queries.append(f"{company_name} {clean_guess}")
    
    elif search_type == 'linkedin':
        queries = [
            f"{company_name} site:linkedin.com/company",
            f"{company_name} linkedin",
            f"{company_name} ai linkedin",
        ]
        
        # Add query with LLM guess
        if llm_guesses and isinstance(llm_guesses, str):
            if 'linkedin.com/company/' in llm_guesses:
                slug = llm_guesses.split('/company/')[-1].rstrip('/')
                if slug:
                    queries.append(f"{company_name} {slug}")
    
    all_urls = []
    for query in queries:
        try:
            urls = safe_tavily_search(query, search_depth="basic", max_results=5, max_retries=2)
            all_urls.extend(urls)
            if urls:  # If results found, stop
                break
        except Exception as e:
            logger.warning(f"Query failed: {query} - {e}")
            continue
    
    return all_urls

def verify_and_clean_url(url, company_name):
    """Verify and clean URL"""
    if not url:
        return ""
    
    # Add protocol if missing
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    # Check if URL is valid
    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            return ""
    except Exception:
        return ""
    
    return url

def resolve_final_links_with_llm(urls_with_scores, company_name, url_type="website", top_n=3):
    """Use LLM to rerank and select the best link"""
    if not urls_with_scores:
        return ""
    
    # Sort by score and get top N
    sorted_urls = sorted(urls_with_scores, key=lambda x: x[1], reverse=True)[:top_n]
    
    if len(sorted_urls) == 1:
        return sorted_urls[0][0]
    
    # Create prompt for LLM
    prompt = f"You are an expert startup analyst. Please select the correct {url_type} for the company '{company_name}' from the following list:\n\n"
    
    for i, (url, score) in enumerate(sorted_urls, 1):
        title = fetch_title(url)
        domain = get_domain_root(url)
        prompt += f"{i}. {url} (domain: {domain}, score: {score}, title: {title})\n"
    
    prompt += f"\nReturn JSON: {{\"best_url\": \"Best URL\", \"reason\": \"Reason for selection\"}}"
    
    content = llm_prompt(prompt, max_tokens=256)
    if not content:
        return sorted_urls[0][0]  # Fallback to highest score
    
    result = safe_parse_json(content)
    if result and result.get('best_url'):
        logger.info(f"[LLM RERANK] {company_name} -> {result.get('best_url')} | reason: {result.get('reason', '')}")
        return result.get('best_url')
    
    return sorted_urls[0][0]  # Fallback to highest score

def find_company_website_llm(company_name, context=""):
    prompt = (
        f"What is the official website of the startup company named '{company_name}'{f', {context}' if context else ''}? Only return the URL, nothing else. If you are not sure, return 'unknown'."
    )
    response = llm_prompt(prompt)
    url = response.choices[0].message.content.strip()
    if url.startswith('http'):
        return url, False
    if url.lower() != 'unknown':
        return url, True
    return '', True

def find_company_linkedin_llm(company_name, context=""):
    prompt = (
        f"What is the LinkedIn page URL of the startup company named '{company_name}'{f', {context}' if context else ''}? Only return the URL, nothing else. If you are not sure, return 'unknown'."
    )
    response = llm_prompt(prompt)
    url = response.choices[0].message.content.strip()
    if url.startswith('http') and "linkedin.com/company" in url:
        return url, False
    if url.lower() != 'unknown':
        return url, True
    return '', True

def verify_link_with_tavily(link, company_name, is_linkedin=False):
    if not link or not isinstance(link, str):
        return False
    normalized = normalize_name(company_name)
    queries = [
        f"{company_name} official website",
        f"{company_name} ai",
        f"{company_name} dev",
        f"{company_name} tech",
        f"{company_name} inc",
        f"{company_name} corp",
        f"{company_name} startup",
        f"{company_name} company",
    ]
    if is_linkedin:
        queries = [f"{company_name} site:linkedin.com/company"]
    for query in queries:
        try:
            urls = safe_tavily_search(query, search_depth="basic", max_results=5)
            for url in urls:
                domain = urlparse(url).netloc
                slug = domain.split(".")[0]
                score = fuzz.partial_ratio(slug.lower(), normalized)
                if link.replace('LLM_guess: ', '').strip().lower() in url.strip().lower() or url.strip().lower() in link.replace('LLM_guess: ', '').strip().lower():
                    if score >= 80:
                            logger.info(f"[TAVILY][VERIFY][MATCH] {company_name} | Query: {query} | URL: {url} | score: {score}")
            return True
        except Exception as e:
            logger.error(f"[ERROR][TAVILY VERIFY] {company_name} | Query: {query} | {e}")
            if '429' in str(e):
                logger.warning('[TAVILY][BLOCKED] Tavily is blocking, please try again later or increase sleep time!')
    logger.warning(f"[TAVILY][VERIFY][FAIL] {company_name} | Could not verify link via Tavily.")
    return False 

def search_company_links(company_name, type='website', top_k=5):
    """
    Find top_k website or LinkedIn links for a company, return list [(url, score, title, reason)]
    """
    queries = []
    if type == 'website':
        queries = [
            f"{company_name} official site",
            f"{company_name} homepage",
            f"{company_name} ai official site",
            f"{company_name} tech official site",
            f"{company_name} company",
        ]
        site_filter = None
    else:
        queries = [
            f"{company_name} site:linkedin.com",
            f"{company_name} ai site:linkedin.com",
            f"{company_name} tech site:linkedin.com",
            f"{company_name} company site:linkedin.com",
        ]
        site_filter = "linkedin.com/company"
    results = []
    for query in queries:
        try:
            links = safe_tavily_search(query, search_depth="basic", max_results=top_k)
            for url in links:
                if type == 'website' and any(ext in url for ext in ['.com', '.ai', '.io', '.co', '.net', '.org', '.dev', '.app']):
                    results.append(url)
                elif type == 'linkedin' and site_filter and site_filter in url:
                    results.append(url)
        except Exception as e:
            logger.error(f"[ERROR][TAVILY COMPANY LINKS] {company_name} | Query: {query} | {e}")
            if '429' in str(e):
                logger.warning('[TAVILY][BLOCKED] Tavily is blocking, please try again later or increase sleep time!')
            continue
        if len(results) >= top_k:
            break
    # Remove duplicates
    results = list(dict.fromkeys(results))[:top_k]
    scored = []
    for url in results:
        ok, score, title, reason = verify_link_match(company_name, url, type)
        scored.append((url, score, title, reason))
    return scored

def verify_link_match(company_name, url, type='website'):
    """
    Verify link based on domain, title, meta, slug. Returns (True/False, score, title, reason)
    """
    try:
        resp = requests.get(url, timeout=7)
        html = resp.text
        title = ''
        meta_desc = ''
        og_title = ''
        # Get title
        m = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
        if m:
            title = m.group(1)
        # Get meta description
        m = re.search(r'<meta name=["\']description["\'] content=["\'](.*?)["\']', html, re.IGNORECASE)
        if m:
            meta_desc = m.group(1)
        # Get og:title
        m = re.search(r'<meta property=["\']og:title["\'] content=["\'](.*?)["\']', html, re.IGNORECASE)
        if m:
            og_title = m.group(1)
        # Match domain
        domain = url.split('//')[-1].split('/')[0].split('.')[0]
        company_key = company_name.lower().replace(' ', '').replace('-', '')
        domain_score = fuzz.ratio(company_key, domain.replace('-', '').replace('_', ''))
        title_score = fuzz.ratio(company_name.lower(), title.lower()) if title else 0
        meta_score = fuzz.ratio(company_name.lower(), meta_desc.lower()) if meta_desc else 0
        og_score = fuzz.ratio(company_name.lower(), og_title.lower()) if og_title else 0
        # LinkedIn slug
        slug_score = 0
        if type == 'linkedin' and 'linkedin.com/company/' in url:
            slug = url.split('linkedin.com/company/')[-1].split('/')[0].replace('-', '').replace('_', '').lower()
            slug_score = fuzz.ratio(company_key, slug)
        # Heuristic: >=2 factors > 70 are valid
        factors = [domain_score, title_score, meta_score, og_score, slug_score]
        pass_count = sum([s > 70 for s in factors])
        score = max(factors)
        if pass_count >= 2:
            return True, score, title, f"Pass: domain={domain_score}, title={title_score}, meta={meta_score}, og={og_score}, slug={slug_score}"
        else:
            return False, score, title, f"Fail: domain={domain_score}, title={title_score}, meta={meta_score}, og={og_score}, slug={slug_score}"
    except Exception as e:
        return False, 0, '', f"Error: {e}"

def resolve_final_links(company_name, type='website', use_llm=False):
    """
    Return the best (website/linkedin) link for a company, optionally using LLM rerank.
    """
    scored = search_company_links(company_name, type=type, top_k=5)
    # If not using LLM rerank, take the link with the highest score and pass verification
    best = None
    best_score = 0
    for url, score, title, reason in scored:
        if score > best_score and 'Pass' in reason:
            best = url
            best_score = score
    if best or not use_llm:
        return best
    # If wanting to use LLM rerank (when no pass link or wanting to be more confident)
    if use_llm and scored:
        prompt = f"""
Given the company name '{company_name}', choose the correct {type} from the following list:\n"""
        for i, (url, score, title, reason) in enumerate(scored, 1):
            prompt += f"{i}. {url} (title: {title})\n"
        prompt += "\nReturn only the number of the best match."
        response = llm_prompt(prompt)
        content = response.choices[0].message.content.strip()
        try:
            idx = int(content)
            if 1 <= idx <= len(scored):
                return scored[idx-1][0]
        except Exception:
            pass
    return None

# Main functions for external use
def find_company_website(company_name: str) -> str:
    """
    Find company website using Tavily search with enhanced matching
    """
    if not company_name:
        return ""
    
    logger.info(f"Searching for website: {company_name}")
    
    # Try Tavily search first
    website = search_tavily_website(company_name)
    if website:
        return website
    
    # Fallback to LLM guess
    logger.info(f"Tavily search failed, trying LLM guess for: {company_name}")
    llm_guess, is_ambiguous = find_company_website_llm(company_name)
    if llm_guess and not is_ambiguous:
        return llm_guess
    
    return ""

def find_company_linkedin(company_name: str) -> str:
    """
    Find company LinkedIn using Tavily search with enhanced matching
    """
    if not company_name:
        return ""
        
    logger.info(f"Searching for LinkedIn: {company_name}")
    
    # Try Tavily search first
    linkedin = search_tavily_linkedin(company_name)
    if linkedin:
        return linkedin
    
    # Fallback to LLM guess
    logger.info(f"Tavily search failed, trying LLM guess for: {company_name}")
    llm_guess, is_ambiguous = find_company_linkedin_llm(company_name)
    if llm_guess and not is_ambiguous:
        return llm_guess
    
    return ""

def verify_company_info(company_name: str, website: str = "", linkedin: str = "") -> dict:
    """
    Verify company information using multiple methods
    """
    result = {
        'company_name': company_name,
        'website': website,
        'linkedin': linkedin,
        'verified': False,
        'confidence': 'low'
    }
    
    # Verify website if provided
    if website:
        page_content = fetch_page_content(website, max_chars=500)
        if verify_url_with_llm(website, company_name, "website", context=page_content):
            result['website_verified'] = True
            result['confidence'] = 'medium'
    
    # Verify LinkedIn if provided
    if linkedin:
        page_content = fetch_page_content(linkedin, max_chars=500)
        if verify_url_with_llm(linkedin, company_name, "LinkedIn", context=page_content):
            result['linkedin_verified'] = True
            result['confidence'] = 'high' if result.get('website_verified') else 'medium'
    
    # Overall verification
    if result.get('website_verified') or result.get('linkedin_verified'):
        result['verified'] = True
    
    return result