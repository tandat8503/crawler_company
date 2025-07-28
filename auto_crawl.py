import requests
from bs4 import BeautifulSoup
import csv
import os
from datetime import datetime, timedelta, date, timezone
from urllib.parse import urlparse
import json
from dotenv import load_dotenv
import openai
import config
import validators
from googlesearch import search as google_search_lib
import re
from collections import OrderedDict
try:
    from thefuzz import fuzz
except ImportError:
    print('[WARNING] thefuzz is not installed. Please run: pip install thefuzz')
    fuzz = None

import pandas as pd
from llm_utils import (
    extract_company_name_and_raised_date_llm, extract_funding_info_llm,
    is_funding_article_llm, is_negative_news
)
from deduplication import (
    normalize_company_name, normalize_amount, normalize_date, deduplicate_csv,
    load_existing_entries, get_existing_keys, verify_and_normalize_link
)
from search_utils import (
    search_google_website, search_google_linkedin, find_company_website_llm,
    find_company_linkedin_llm, verify_link_with_google, get_whitelisted_links
)
import time

CSV_FILE = config.CSV_FILE
TECHCRUNCH_URL = 'https://techcrunch.com/category/startups/'
HEADERS = config.HEADERS

# Load API key from config or .env
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

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

def get_article_links_last_7_days(min_date=None, max_pages=5):
    """
    Crawl TechCrunch Startups page, get all articles in the date range [min_date, today], stop when all articles on the page are older than min_date.
    Use requests + BeautifulSoup, do not use Selenium.
    Updated to support new TechCrunch HTML structure (2023+)
    """
    import logging
    links = []
    today = datetime.now(timezone.utc).date()
    if min_date is None:
        min_date = today - timedelta(days=3)
    for page in range(1, max_pages+1):
        page_url = f"https://techcrunch.com/category/startups/page/{page}/"
        print(f"[INFO] Crawling page {page}: {page_url}")
        try:
            resp = requests.get(page_url, headers={'User-Agent': 'Mozilla/5.0 (compatible; CompanyFundBot/1.0)'}, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            print(f"[ERROR] Failed to fetch page {page}: {e}")
            break
        soup = BeautifulSoup(resp.text, 'html.parser')
        # New selector: article.wp-block-tc2023-post-card
        cards = soup.find_all('article', class_='wp-block-tc2023-post-card')
        print(f"Page {page}: Found {len(cards)} articles with 'wp-block-tc2023-post-card'")
        # Fallbacks
        if not cards:
            cards = soup.find_all('div', class_='wp-block-techcrunch-card')
            print(f"Page {page}: Found {len(cards)} cards with 'wp-block-techcrunch-card' (fallback)")
        if not cards:
            cards = soup.find_all('article')
            print(f"Page {page}: Found {len(cards)} generic 'article' tags (fallback)")
        if not cards:
            cards = soup.find_all('div', class_=lambda x: x and 'card' in x)
            print(f"Page {page}: Found {len(cards)} divs with 'card' in class (fallback)")
        if not cards:
            print(f"[WARNING] No article cards found on page {page}. Check selector.")
        all_older = True
        for card in cards:
            # New selector for link: h2.wp-block-tc2023-post-card__title > a
            h2 = card.find('h2', class_='wp-block-tc2023-post-card__title')
            a_tag = h2.find('a') if h2 else None
            if not a_tag:
                # Fallback to old selector
                content = card.find('div', class_='loop-card__content')
                h3 = content.find('h3', class_='loop-card__title') if content else None
                a_tag = h3.find('a', class_='loop-card__title-link', href=True) if h3 else None
            if a_tag:
                url = a_tag['href']
                print(f"Found URL: {url}")
                # New selector for time
                time_tag = card.find('time')
                if time_tag and time_tag.has_attr('datetime'):
                    try:
                        pub_date = datetime.fromisoformat(time_tag['datetime'].replace('Z', '+00:00')).date()
                        print(f"Found date: {pub_date} from datetime: {time_tag['datetime']}")
                    except Exception as e:
                        print(f"Error parsing date: {e}")
                        pub_date = today
                else:
                    print("No time tag found with datetime attribute, using today's date")
                    pub_date = today
                if min_date <= pub_date <= today:
                    links.append((url, pub_date.isoformat()))
                    all_older = False
            else:
                print("No main article link (a_tag) found in card")
        if all_older:
            break
    return links


def extract_article_detail(url):
    resp = requests.get(url, headers=HEADERS, timeout=10)
    soup = BeautifulSoup(resp.text, 'html.parser')
    # Title
    title_tag = soup.find('h1')
    title = title_tag.get_text(strip=True) if title_tag else ""
    # Content
    content_div = soup.find('div', class_='entry-content')
    article_text = ""
    if content_div:
        paragraphs = content_div.find_all('p')
        article_text = " ".join(p.get_text() for p in paragraphs)
    # Publication date
    time_tag = soup.find('time')
    if time_tag and time_tag.has_attr('datetime'):
        try:
            pub_date = datetime.fromisoformat(time_tag['datetime'].replace('Z', '+00:00')).date().isoformat()
        except Exception:
            pub_date = ""
    else:
        pub_date = ""
    return {
        "title": title,
        "content": article_text,
        "pub_date": pub_date,
        "url": url
    }


def extract_company_name_and_raised_date_llm(article_text, min_date, max_date):
    prompt = (
        "Given the following news article about a company raising funds, extract:\n"
        "- The company name\n"
        "- The date the company raised funds (if available, in YYYY-MM-DD format, else empty)\n"
        f"Only extract the date if it is between {min_date} and {max_date}. If not, leave raised_date empty.\n"
        "Return the result as JSON with keys: company_name, raised_date. Only return valid JSON, nothing else.\n\n"
        f"Article:\n{article_text}\n\nJSON:"
    )
    response = openai.chat.completions.create(
        model=config.LLM_MODEL_ID,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=128,
        temperature=0
    )
    content = response.choices[0].message.content.strip()
    try:
        return json.loads(content)
    except Exception as e:
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
        print(f"LLM JSON parse error: {e}\nLLM content: {content}")
        return None

def find_company_website_llm(company_name, context=""):
    prompt = (
        f"What is the official website of the startup company named '{company_name}'{f', {context}' if context else ''}? Only return the URL, nothing else. If you are not sure, return 'unknown'."
    )
    response = openai.chat.completions.create(
        model=config.LLM_MODEL_ID,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=32,
        temperature=0
    )
    url = response.choices[0].message.content.strip()
    if is_valid_url(url):
        print(f"[DEBUG][LLM WEBSITE] {company_name} | {url}")
        return url, False  # False = ambiguous
    if url.lower() != 'unknown':
        print(f"[DEBUG][LLM WEBSITE GUESS] {company_name} | {url}")
        return url, True  # True = ambiguous
    return '', True


def find_company_linkedin_llm(company_name, context=""):
    prompt = (
        f"What is the LinkedIn page URL of the startup company named '{company_name}'{f', {context}' if context else ''}? Only return the URL, nothing else. If you are not sure, return 'unknown'."
    )
    response = openai.chat.completions.create(
        model=config.LLM_MODEL_ID,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=32,
        temperature=0
    )
    url = response.choices[0].message.content.strip()
    if is_valid_url(url) and "linkedin.com/company" in url:
        print(f"[DEBUG][LLM LINKEDIN] {company_name} | {url}")
        return url, False
    if url.lower() != 'unknown':
        print(f"[DEBUG][LLM LINKEDIN GUESS] {company_name} | {url}")
        return url, True
    return '', True


def is_negative_news(article_text):
    negative_keywords = [
        'fraud', 'bankruptcy', 'indictment', 'lawsuit', 'arrested', 'charged', 'scandal',
        'liquidation', 'shut down', 'shutting down', 'filed for bankruptcy', 'criminal', 'prosecutor',
        'investigation', 'pleaded guilty', 'pleaded not guilty', 'convicted', 'guilty', 'not guilty',
        'sued', 'sues', 'sue', 'settlement', 'class action', 'fined', 'penalty', 'violation', 'embezzle',
        'money laundering', 'resigned', 'resignation', 'fired', 'terminated', 'layoff', 'layoffs', 'shut',
        'liquidate', 'liquidated', 'liquidating', 'collapse', 'scam', 'debt', 'default', 'insolvency',
        'winding up', 'dissolve', 'dissolved', 'dissolving', 'cease operations', 'ceasing operations',
        'shutter', 'shuttered', 'shuttering', 'closure', 'closed', 'closing', 'shut down', 'shutting down',
        # Exclude IPO articles
        'ipo', 'initial public offering', 'public listing', 'go public', 'roadshow ipo', 'filed for ipo', 
        'files for ipo', 'plans ipo', 'prepares ipo', 'preparing ipo', 'ipo roadshow', 'ipo filing', 
        'ipo debut', 'ipo launch', 'ipo process', 'ipo date', 'ipo price', 'ipo shares', 'ipo valuation', 
        'ipo prospectus', 'ipo registration', 'ipo application', 'ipo approval', 'ipo announcement', 'ipo news', 
        'ipo update', 'ipo event', 'ipo timeline', 'ipo underwriter', 'ipo syndicate', 'ipo investor', 'ipo market', 
        'ipo proceeds', 'ipo capital', 'ipo round', 'ipo funding', 'ipo raise', 'ipo offering', 'ipo float', 
        'ipo subscription', 'ipo oversubscription', 'ipo allocation', 'ipo allotment', 'ipo performance', 
        'ipo trading', 'ipo listing', 'ipo exchange', 'ipo ticker', 'ipo symbol', 'ipo stock', 'ipo equity', 
        'ipo sale', 'ipo buy', 'ipo sell', 'ipo invest', 'ipo investment', 'ipo institutional', 'ipo retail', 
        'ipo demand', 'ipo supply', 'ipo book', 'ipo bookbuilding', 'ipo price band', 'ipo price range', 'ipo price discovery', 
        'ipo anchor', 'ipo anchor investor', 'ipo anchor allocation', 'ipo anchor book', 'ipo anchor round', 'ipo anchor shares', 
        'ipo anchor price', 'ipo anchor demand', 'ipo anchor supply', 'ipo anchor bookbuilding', 'ipo anchor price band', 
        'ipo anchor price range', 'ipo anchor price discovery'
    ]
    text = article_text.lower()
    return any(kw in text for kw in negative_keywords)


# Optimize LLM prompt for is_funding_article_llm

def is_funding_article_llm(article_text, debug=False):
    prompt = (
        "Given the following news article, answer only Yes or No: "
        "Is this article PRIMARILY about a company that has JUST SUCCESSFULLY raised new funds (funding, investment, venture round, seed, series A/B/C, etc) for its future development or growth? "
        "Answer Yes if the article is mainly about a NEW funding event, including extension/top-up/add-on to an existing round (e.g. Series B extension, new investors join Series B, etc). "
        "Do NOT answer Yes if the article is mainly about bankruptcy, fraud, lawsuits, indictments, liquidation, company shutdown, IPO, or past funding events. "
        "If the article is about legal troubles, fraud, bankruptcy, or only mentions past funding, answer No. "
        "If the article is about a company that raised funds in the past (not a new funding event), or is about IPO, or is about general industry news, answer No. "
        "If you are not sure, answer No.\n\n"
        f"Article:\n{article_text}\n\nAnswer (Yes or No):"
    )
    response = openai.chat.completions.create(
        model=config.LLM_MODEL_ID,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=8,
        temperature=0
    )
    answer = response.choices[0].message.content.strip().lower()
    if debug:
        print("=== LLM FUNDING CHECK PROMPT ===")
        print(prompt)
        print("Answer (Yes or No):")
        print("=== LLM FUNDING CHECK RESPONSE ===")
        print(answer)
    return answer.startswith("yes")


def extract_funding_info_llm(article_text):
    # 1. Extract entity segment
    candidate_text = extract_candidate_paragraphs(article_text)
    # 2. Clear prompt
    prompt = (
        "Please extract the following information from the paragraph:\n"
        "1. The newly established or recently raised capital company name\n"
        "2. The official website (if not in the paragraph, leave empty)\n"
        "3. The company's LinkedIn profile (if not in the paragraph, leave empty)\n"
        "4. The date the company raised funds (if available, in YYYY-MM-DD format, else empty)\n"
        "The result should be returned in JSON format with keys: company_name, website, linkedin, raised_date.\n"
        "Only return JSON, nothing else.\n\n"
        f"Paragraph:\n{candidate_text}\n\nJSON:"
    )
    response = openai.chat.completions.create(
        model=config.LLM_MODEL_ID,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=256,
        temperature=0
    )
    import json, re
    content = response.choices[0].message.content.strip()
    try:
        result = json.loads(content)
    except Exception as e:
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(0))
            except Exception:
                result = None
        else:
            print(f"LLM JSON parse error: {e}\nLLM content: {content}")
            result = None
    # 3. Fallback search if website/linkedin is missing
    if result:
        company_name = result.get('company_name', '').strip()
        # Fallback website
        if not result.get('website') and company_name:
            from search_utils import search_google_website
            result['website'] = search_google_website(company_name)
        # Fallback linkedin
        if not result.get('linkedin') and company_name:
            from search_utils import search_google_linkedin
            result['linkedin'] = search_google_linkedin(company_name)
    return result

def extract_candidate_paragraphs(article_text):
    """
    Return the first 2 paragraphs (split by double newlines or periods) as candidate text for LLM extraction.
    """
    if not article_text:
        return ""
    paras = [p.strip() for p in article_text.split('\n') if p.strip()]
    if len(paras) >= 2:
        return '\n'.join(paras[:2])
    # fallback: try splitting by period
    sentences = article_text.split('.')
    return '.'.join(sentences[:4])


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

def extract_best_links_from_anchors(links_context, company_name):
    """
    Optimize selection of website/linkedin from crawled anchors.
    - Website: Prioritize fuzzy match with company name, common domains (.com, .ai, .io, ...)
    - LinkedIn: Domain contains 'linkedin.com' or anchor/context contains 'linkedin'
    """
    from thefuzz import fuzz
    company_norm = company_name.lower().replace(" ", "")
    website = ''
    linkedin = ''
    best_score = 0
    best_url = ''
    # Website
    for link in links_context:
        url = link['url']
        anchor = link['anchor_text'].strip().lower()
        context = link['context'].strip().lower()
        domain = link['domain']
        # Prioritize LinkedIn
        if ('linkedin.com' in domain or 'linkedin' in anchor or 'linkedin' in context) and not linkedin:
            linkedin = url
        # Fuzzy match anchor/context with company name
        anchor_norm = anchor.replace(" ", "")
        context_norm = context.replace(" ", "")
        score_anchor = fuzz.partial_ratio(company_norm, anchor_norm)
        score_context = fuzz.partial_ratio(company_norm, context_norm)
        # Prioritize common domains
        is_good_domain = any(domain.endswith(ext) for ext in ['.com', '.ai', '.io', '.co', '.org'])
        # Select website if good match
        if (score_anchor >= 80 or score_context >= 80) and is_good_domain:
            if max(score_anchor, score_context) > best_score:
                best_score = max(score_anchor, score_context)
                best_url = url
        # If anchor is company name and domain is valid
        elif anchor == company_name.lower() and is_good_domain:
            if 100 > best_score:
                best_score = 100
                best_url = url
    if best_url:
        website = best_url
    return website, linkedin


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


def extract_company_info(article_url):
    """
    Extract company name, website, and date from a TechCrunch article.
    Prioritize website/linkedin from anchor, if not available, use LLM, if still not available, fallback Google.
    """
    try:
        resp = requests.get(article_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        # Get article content
        article_body = soup.find('div', class_='entry-content')
        article_text = ""
        if article_body:
            paragraphs = article_body.find_all('p')
            article_text = " ".join(p.get_text() for p in paragraphs)
        # 1. Prioritize getting link from anchor
        company_name = ''
        website = ''
        linkedin = ''
        links_context = extract_article_links_and_context(soup, company_name)
        website, linkedin = extract_best_links_from_anchors(links_context, company_name)
        # 2. If not available, use LLM with new prompt
        if not website or not linkedin:
            prompt = (
                "You are a startup analyst. Below is a news article about a startup. Your task:\n"
                "- Extract the official website (if mentioned in the article, or in any anchor/link).\n"
                "- Extract the official LinkedIn profile (if mentioned in the article, or in any anchor/link).\n"
                "- If not explicitly mentioned, use reasoning to infer the most likely official website and LinkedIn profile for the company, based on the company name and context.\n"
                "- If you cannot find the website, try to guess up to 3 possible domains based on the company name (e.g. alix.com, alix.ai, getalix.com, alixofficial.com, ...), and rank them by likelihood.\n"
                "- For each guess, explain your reasoning.\n"
                "- If you cannot find the LinkedIn, try to guess the most likely LinkedIn URL (e.g. https://www.linkedin.com/company/alix-ai/).\n"
                "- Return your answer in JSON format, including:\n"
                "  {\n    'company_name': '',\n    'website': '',\n    'website_guesses': ['', '', ''],\n    'linkedin': '',\n    'linkedin_guess': '',\n    'confidence': 'high/medium/low',\n    'reasoning': ''\n  }\n"
                f"\nArticle:\n\"\"\"{article_text}\"\"\"\n"
                f"Links in article: {links_context}\n"
            )
            response = openai.chat.completions.create(
                model=config.LLM_MODEL_ID,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=512,
                temperature=0
            )
            import json, re
            content = response.choices[0].message.content.strip()
            try:
                result = json.loads(content)
            except Exception as e:
                match = re.search(r'\{.*\}', content, re.DOTALL)
                if match:
                    try:
                        result = json.loads(match.group(0))
                    except Exception:
                        result = None
                else:
                    print(f"LLM JSON parse error: {e}\nLLM content: {content}")
                    result = None
            if result:
                company_name = result.get('company_name', '').strip()
                if not website:
                    website = result.get('website', '').strip()
                    # If website is still empty, try to get from website_guesses
                    if not website:
                        guesses = result.get('website_guesses', [])
                        if guesses and isinstance(guesses, list):
                            website = guesses[0].strip() if guesses[0] else ''
                if not linkedin:
                    linkedin = result.get('linkedin', '').strip()
                    if not linkedin:
                        linkedin = result.get('linkedin_guess', '').strip()
                print(f"[LLM][REASONING] {company_name} | confidence: {result.get('confidence', '')} | reasoning: {result.get('reasoning', '')}")
        # 3. If still not available, fallback Google with multiple variations of query
        def google_search_variants(company_name, type_):
            from search_utils import safe_google_search
            queries = []
            if type_ == 'website':
                queries = [
                    f"{company_name} official site",
                    f"{company_name} ai",
                    f"{company_name} homepage",
                    f"{company_name} {company_name.split()[-1]}",
                    f"{company_name} site:.ai OR site:.com OR site:.io",
                ]
            elif type_ == 'linkedin':
                queries = [
                    f"{company_name} site:linkedin.com/company",
                    f"{company_name} linkedin",
                    f"{company_name} ai linkedin",
                ]
            for query in queries:
                urls = safe_google_search(query, num_results=8)
                if urls:
                    return urls
            return []
        if not website and company_name:
            # Try multiple Google query variations
            urls = google_search_variants(company_name, 'website')
            if urls:
                from search_utils import search_google_website
                website = search_google_website(company_name)
        if not linkedin and company_name:
            urls = google_search_variants(company_name, 'linkedin')
            if urls:
                from search_utils import search_google_linkedin
                linkedin = search_google_linkedin(company_name)
        # Get article publication date
        date_tag = soup.find('time')
        if date_tag and date_tag.has_attr('datetime'):
            date = datetime.fromisoformat(date_tag['datetime'].replace('Z', '+00:00')).date().isoformat()
        else:
            date = datetime.utcnow().date().isoformat()
        return {
            'date': date,
            'company_name': company_name,
            'website': website,
            'linkedin': linkedin,
            'article_url': article_url,
        }
    except Exception as e:
        print(f"[ERROR] {article_url} | {e}")
        return None


# Optimize duplicate removal when saving to CSV

def normalize_company_name(name):
    """
    Normalize company name: remove common suffixes, punctuation, lowercase, remove common words.
    """
    if not name:
        return ''
    name = name.lower()
    # Remove common suffixes
    blacklist = [
        'inc', 'ltd', 'corp', 'co', 'corporation', 'limited', 'llc', 'plc', 'group', 'holdings', 'holding', 'company', 'companies',
        'sas', 'sa', 'pte', 'group', 'ventures', 'ai', 'robotics', 'systems', 'solutions', 'partners', 'capital',
        'inc.', 'ltd.', 'corp.', 'co.', 'group.', 'ventures.', 'ai.', 'robotics.', 'systems.', 'solutions.', 'partners.', 'capital.', 'holdings.', 'company.', 'co.', 'llc.', 'plc.', 'limited.', 'ltd.'
    ]
    for word in blacklist:
        name = re.sub(r'\b' + word + r'\b', '', name)
    name = re.sub(r'[^a-z0-9]', '', name)  # Remove punctuation, spaces
    return name.strip()

def normalize_amount(amount):
    # Normalize funding amount to number (float, million USD)
    if not amount:
        return None
    import re
    s = str(amount).replace(",", "").lower()
    m = re.search(r"([\d\.]+)\s*(m|million|b|billion|k|thousand)?", s)
    if not m:
        return None
    val = float(m.group(1))
    unit = m.group(2)
    if unit in ["b", "billion"]:
        val = val * 1000
    elif unit in ["k", "thousand"]:
        val = val / 1000
    # Default to million USD
    return round(val, 2)

def normalize_date(date_str):
    if not date_str:
        return ''
    import re
    date_str = str(date_str).strip()
    # If already in yyyy-mm-dd format
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').strftime('%Y-%m-%d')
    except:
        pass
    # If dạng "July 22, 2025"
    try:
        return datetime.strptime(date_str, '%B %d, %Y').strftime('%Y-%m-%d')
    except:
        pass
    # If dạng "July 22,2025" (missing space)
    try:
        return datetime.strptime(date_str.replace(',', ', '), '%B %d, %Y').strftime('%Y-%m-%d')
    except:
        pass
    # If dạng "22 July 2025"
    try:
        return datetime.strptime(date_str, '%d %B %Y').strftime('%Y-%m-%d')
    except:
        pass
    # If dạng "2025/07/22"
    try:
        return datetime.strptime(date_str, '%Y/%m/%d').strftime('%Y-%m-%d')
    except:
        pass
    # If dạng "2025.07.22"
    try:
        return datetime.strptime(date_str, '%Y.%m.%d').strftime('%Y-%m-%d')
    except:
        pass
    # If dạng "22/07/2025"
    try:
        return datetime.strptime(date_str, '%d/%m/%Y').strftime('%Y-%m-%d')
    except:
        pass
    # If dạng "22.07.2025"
    try:
        return datetime.strptime(date_str, '%d.%m.%Y').strftime('%Y-%m-%d')
    except:
        pass
    # If not parseable, return original string
    return date_str

def deduplicate_csv():
    import csv
    import os
    from collections import OrderedDict
    if not os.path.exists(CSV_FILE):
        return
    fieldnames = ['raised_date', 'company_name', 'website', 'linkedin', 'article_url', 'source', 'amount', 'industry', 'crawl_date']
    rows = []
    with open(CSV_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    # Deduplicate by (company, date, amount) prioritizing TechCrunch, if amount is missing, only compare (company, date)
    seen = OrderedDict()
    for row in rows:
        name = normalize_company_name(row.get('company_name', ''))
        date = normalize_date(row.get('raised_date', ''))
        amount = normalize_amount(row.get('amount', ''))
        key_full = (name, date, amount)
        key_noval = (name, date)
        # If a TechCrunch entry with the same key already exists, skip the new entry
        if amount is not None:
            if key_full in seen:
                # Prioritize TechCrunch
                if seen[key_full]['source'] == 'TechCrunch':
                    continue
                if row['source'] == 'TechCrunch':
                    seen[key_full] = row
                continue
            seen[key_full] = row
        else:
            if key_noval in seen:
                if seen[key_noval]['source'] == 'TechCrunch':
                    continue
                if row['source'] == 'TechCrunch':
                    seen[key_noval] = row
                continue
            seen[key_noval] = row
    # Write back to file
    with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in seen.values():
            writer.writerow(row)

# Fix load_existing_entries function

def load_existing_entries():
    entries = {}
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = (
                    normalize_company_name(row.get('company_name', '')),
                    row.get('article_url', '').strip()
                )
                entries[key] = row.get('source', '')
    return entries


def save_to_csv(entries):
    """
    Save a list of dicts to CSV, appending if file exists.
    Before saving, deduplicate using pandas by ['company_name', 'article_url'].
    """
    import csv
    import os
    import pandas as pd
    fieldnames = ['raised_date', 'company_name', 'website', 'linkedin', 'article_url', 'source', 'amount', 'industry', 'crawl_date']
    file_exists = os.path.exists(CSV_FILE)
    # Save temporarily to file
    temp_file = CSV_FILE + ".tmp"
    with open(temp_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in entries:
            writer.writerow(row)
    # Read back by pandas and deduplicate
    df = pd.read_csv(temp_file)
    df = df.drop_duplicates(subset=["company_name", "article_url"], keep="first")
    df.to_csv(CSV_FILE, index=False)
    os.remove(temp_file)
    print(f"[INFO][DEDUP] Saved {len(df)} unique entries to {CSV_FILE}")


def find_company_website(company_name, context=""):
    url = find_company_website_llm(company_name, context)
    if is_valid_url(url):
        return url
    url = search_google_website(company_name)
    return url or ""

def find_linkedin_from_website(website_url, company_name=None):
    import requests
    from bs4 import BeautifulSoup
    try:
        resp = requests.get(website_url, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        candidates = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "linkedin.com/company" in href or "linkedin.com/" in href:
                if href.startswith("//"):
                    href = "https:" + href
                elif href.startswith("/"):
                    href = website_url.rstrip("/") + href
                candidates.append(href)
        if company_name:
            key = company_name.lower().replace(' ', '').replace('-', '')
            for href in candidates:
                if key in href.lower().replace('-', ''):
                    return href
        if candidates:
            return candidates[0]
    except Exception as e:
        print(f"[DEBUG] Error crawling website for LinkedIn: {e}")
    return ""

def find_company_linkedin(company_name, website=None, context=""):
    linkedin = ""
    if website:
        linkedin = find_linkedin_from_website(website, company_name)
        if linkedin:
            return linkedin
    # Fallback: SerpAPI
    return search_google_linkedin(company_name, context)


def get_article_publish_date(soup):
    time_tag = soup.find('time')
    if time_tag and time_tag.has_attr('datetime'):
        try:
            return time_tag['datetime'][:10]  # YYYY-MM-DD
        except Exception:
            pass
    return ""

def llm_verify_url(company_name, url, url_type, news_context):
    prompt = (
        f"Is this {url_type} the official {url_type} of the company '{company_name}' mentioned in the following news?\n"
        f"News: {news_context}\n"
        f"{url_type.capitalize()}: {url}\n"
        "Answer only Yes or No."
    )
    response = openai.chat.completions.create(
        model=config.LLM_MODEL_ID,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=8,
        temperature=0
    )
    answer = response.choices[0].message.content.strip().lower()
    return answer.startswith("yes")

def search_and_verify_website(company_name, news_context):
    query = f"{company_name} official website {news_context}" if news_context else f"{company_name} official website"
    results = google_search_lib(query, num=5)
    tried_links = []
    for r in results:
        url = r.get("link", "")
        if url and is_valid_url(url):
            is_valid = llm_verify_url(company_name, url, "website", news_context)
            tried_links.append((url, is_valid))
            if is_valid:
                return url
    print(f"[DEBUG][NO VALID WEBSITE] {company_name} | Tried: {[l for l, v in tried_links]} | LLM: {[v for l, v in tried_links]}")
    return ""

def search_and_verify_linkedin(company_name, news_context):
    query = f"{company_name} linkedin {news_context}" if news_context else f"{company_name} linkedin"
    results = google_search_lib(query, num=5)
    tried_links = []
    for r in results:
        url = r.get("link", "")
        if "linkedin.com/company" in url and is_valid_url(url):
            is_valid = llm_verify_url(company_name, url, "LinkedIn", news_context)
            tried_links.append((url, is_valid))
            if is_valid:
                return url
    print(f"[DEBUG][NO VALID LINKEDIN] {company_name} | Tried: {[l for l, v in tried_links]} | LLM: {[v for l, v in tried_links]}")
    return ""

def pick_best_website(company_name, urls):
    company_key = normalize_company_name(company_name)
    best_url = ""
    best_score = 0
    for url in urls:
        domain = url.split('//')[-1].split('/')[0].split('.')[0]
        score = fuzz.ratio(company_key, domain.replace('-', '').replace('_', ''))
        if score > best_score:
            best_score = score
            best_url = url
    if best_score >= 80:
        return best_url
    return best_url if best_url else (urls[0] if urls else "")

def pick_best_linkedin(company_name, urls):
    company_key = normalize_company_name(company_name)
    best_url = ""
    best_score = 0
    for url in urls:
        if "linkedin.com/company" in url:
            slug = url.split("linkedin.com/company/")[-1].split("/")[0].replace('-', '').replace('_', '').lower()
            score = fuzz.ratio(company_key, slug)
            if score > best_score:
                best_score = score
                best_url = url
    if best_score >= 80:
        return best_url
    return best_url if best_url else (urls[0] if urls else "")

# Ensure crawl_finsmes_usa function exists
# (If already present in the file, skip this section)
def crawl_finsmes_usa(max_pages=5):
    articles = []
    for page in range(1, max_pages+1):
        url = f"https://www.finsmes.com/category/usa/page/{page}"
        try:
            resp = requests.get(url, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            for meta in soup.find_all("div", class_="td-module-meta-info"):
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
            time.sleep(1)
        except Exception as e:
            print(f"[ERROR][Finsmes] Page {page}: {e}")
    return articles

# Add delay to search_google_website and search_google_linkedin
old_search_google_website = search_google_website
old_search_google_linkedin = search_google_linkedin

def search_google_website(company_name):
    result = old_search_google_website(company_name)
    time.sleep(2)
    return result

def search_google_linkedin(company_name, website=None):
    result = old_search_google_linkedin(company_name, website)
    time.sleep(2)
    return result

def get_domain_from_url(url):
    from urllib.parse import urlparse
    domain = urlparse(url).netloc
    return domain.replace("www.", "").replace(".com", "").replace(".io", "").replace(".ai", "").replace("-", "")

def get_html_title(url):
    try:
        resp = requests.get(url, timeout=8)
        soup = BeautifulSoup(resp.text, "html.parser")
        title = soup.title.string if soup.title else ""
        return title or ""
    except Exception:
        return ""

def is_good_match(company_name, url):
    domain = get_domain_from_url(url)
    name_norm = company_name.lower().replace(" ", "").replace("-", "")
    score = fuzz.partial_ratio(name_norm, domain)
    print(f"[MATCH][WEBSITE] {company_name} vs {domain} | score: {score}")
    if score >= 85:
        return True
    else:
        title = get_html_title(url)
        if title:
            title_score = fuzz.partial_ratio(company_name.lower(), title.lower())
            print(f"[MATCH][WEBSITE][FALLBACK TITLE] {company_name} vs {title} | score: {title_score}")
            if title_score >= 80:
                return True
    return False

def is_good_linkedin_match(company_name, linkedin_url):
    slug = linkedin_url.rstrip("/").split("/")[-1].replace("-", " ")
    score = fuzz.token_set_ratio(company_name.lower(), slug.lower())
    print(f"[MATCH][LINKEDIN] {company_name} vs {slug} | score: {score}")
    return score >= 85

def crawl_techcrunch():
    today = date.today()
    min_date = today - timedelta(days=3)
    article_links = get_article_links_last_7_days(min_date=min_date, max_pages=5)
    print(f'Found {len(article_links)} TechCrunch articles.')
    existing_entries = load_existing_entries()
    unique_entries = {}
    for url, pub_date in article_links:
        source = "TechCrunch"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(resp.text, 'html.parser')
            title_tag = soup.find('h1')
            title = title_tag.get_text(strip=True) if title_tag else ''
            article_body = soup.find('div', class_='entry-content')
            article_text = ""
            if article_body:
                paragraphs = article_body.find_all('p')
                article_text = " ".join(p.get_text() for p in paragraphs)
            else:
                print(f"[SKIP][NO CONTENT] {url}")
                continue
            if not is_funding_article_llm(article_text):
                print(f"[SKIP][NOT FUNDING] Title: {title} | Date: {pub_date} | URL: {url}")
                continue
            info = extract_company_name_and_raised_date_llm(article_text, min_date.isoformat(), today.isoformat())
            if isinstance(info, list):
                infos = info
            else:
                infos = [info]
            for company_info in infos:
                company_name = company_info.get('company_name', '').strip()
                raised_date = company_info.get('raised_date', '').strip() or pub_date
                key = (normalize_company_name(company_name), url)
                if not company_name:
                    print(f"[SKIP][NO COMPANY NAME] Title: {title} | Date: {pub_date} | URL: {url}")
                    continue
                if key in existing_entries or key in unique_entries:
                    print(f"[SKIP][DUPLICATE] {company_name} | {pub_date} | {url}")
                    continue
                website = search_google_website(company_name)
                if website and is_good_match(company_name, website):
                    website = verify_and_normalize_link(company_name, website, link_type='website')
                else:
                    print(f"[WARNING][NO GOOD WEBSITE] {company_name} | {pub_date} | {url} | website: {website}")
                    website = ''
                    linkedin = search_google_linkedin(company_name, website=website)
                if linkedin and is_good_linkedin_match(company_name, linkedin):
                    linkedin = verify_and_normalize_link(company_name, linkedin, link_type='linkedin')
                else:
                    print(f"[WARNING][NO GOOD LINKEDIN] {company_name} | {pub_date} | {url} | linkedin: {linkedin}")
                    linkedin = ''
                crawl_date = today.isoformat()
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
                print(f"[ADD] {company_name} | {pub_date} | {url}")
        except Exception as e:
            print(f"[ERROR] {url} | {e}")
    return list(unique_entries.values())

def crawl_finsmes():
    today = date.today()
    min_date = today - timedelta(days=3)
    finsmes_articles = crawl_finsmes_usa(max_pages=5)
    print(f'Found {len(finsmes_articles)} Finsmes articles.')
    existing_entries = load_existing_entries()
    unique_entries = {}
    for a in finsmes_articles:
        url = a['url']
        pub_date = a['pub_date']
        source = "Finsmes"
        try:
            soup, article_text = extract_finsmes_article_detail(url)
            if not article_text:
                print(f"[SKIP][NO CONTENT] {url}")
                continue
            title_tag = soup.find('h1') if soup else None
            title = title_tag.get_text(strip=True) if title_tag else ''
            if len(article_text) < 300:
                print("[INFO] Skipping article due to insufficient content.")
                continue
            if not is_funding_article_llm(article_text):
                print(f"[SKIP][NOT FUNDING] Title: {title} | Date: {pub_date} | URL: {url}")
                continue
            info = extract_company_name_and_raised_date_llm(article_text, min_date.isoformat(), today.isoformat())
            if isinstance(info, list):
                infos = info
            else:
                infos = [info]
            for company_info in infos:
                company_name = company_info.get('company_name', '').strip()
                raised_date = company_info.get('raised_date', '').strip() or pub_date
                key = (normalize_company_name(company_name), url)
                if not company_name:
                    print(f"[SKIP][NO COMPANY NAME] Title: {title} | Date: {pub_date} | URL: {url}")
                    continue
                if key in existing_entries or key in unique_entries:
                    print(f"[SKIP][DUPLICATE] {company_name} | {pub_date} | {url}")
                    continue
                website = search_google_website(company_name)
                if website and is_good_match(company_name, website):
                    website = verify_and_normalize_link(company_name, website, link_type='website')
                else:
                    print(f"[WARNING][NO GOOD WEBSITE] {company_name} | {pub_date} | {url} | website: {website}")
                    website = ''
                    linkedin = search_google_linkedin(company_name, website=website)
                if linkedin and is_good_linkedin_match(company_name, linkedin):
                    linkedin = verify_and_normalize_link(company_name, linkedin, link_type='linkedin')
                else:
                    print(f"[WARNING][NO GOOD LINKEDIN] {company_name} | {pub_date} | {url} | linkedin: {linkedin}")
                    linkedin = ''
                crawl_date = today.isoformat()
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
                print(f"[ADD] {company_name} | {pub_date} | {url}")
        except Exception as e:
            print(f"[ERROR] {url} | {e}")
    return list(unique_entries.values())

def main():
    tech_entries = crawl_techcrunch()
    if tech_entries:
        save_to_csv(tech_entries)
        print(f'Saved {len(tech_entries)} TechCrunch entries.')
    finsmes_entries = crawl_finsmes()
    if finsmes_entries:
        save_to_csv(finsmes_entries)
        print(f'Saved {len(finsmes_entries)} Finsmes entries.')
    deduplicate_csv()
    print("Done. Check companies.csv for results.")

if __name__ == '__main__':
    main()