import requests
from bs4 import BeautifulSoup
import csv
import os
from datetime import datetime, timedelta, date, timezone
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import json
from dotenv import load_dotenv
import openai
import config
import validators
from googlesearch import search as google_search_lib
import re

CSV_FILE = os.path.join(os.path.dirname(__file__), 'companies.csv')
TECHCRUNCH_URL = 'https://techcrunch.com/category/startups/'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; CompanyFundBot/1.0)'
}

# Load API key từ config hoặc .env
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def check_common_errors():
    import sys
    # 1. Kiểm tra import json
    if 'json' not in sys.modules:
        try:
            import json
            print('[TOOL CALL] Đã tự động import json.')
        except ImportError:
            print('[TOOL CALL][ERROR] Không thể import json. Hãy cài đặt lại Python!')
    # 2. Kiểm tra lỗi parse JSON từ LLM (giả lập)
    try:
        import json
        test = json.loads('{"a": 1}')
    except Exception as e:
        print(f'[TOOL CALL][ERROR] Lỗi parse JSON: {e}')
    # 3. Kiểm tra lỗi truy cập thuộc tính của None
    try:
        none_obj = None
        none_obj.get('a')
    except AttributeError:
        print('[TOOL CALL] Đã phát hiện lỗi truy cập thuộc tính của None. Hãy kiểm tra lại kết quả trả về từ LLM hoặc các hàm extract.')
    except Exception as e:
        print(f'[TOOL CALL][ERROR] Lỗi không xác định khi truy cập thuộc tính của None: {e}')

# Gọi tool call này ở đầu script
check_common_errors()

def get_article_links_last_7_days(min_date=None, max_pages=5):
    """
    Crawl TechCrunch Startups page, lấy tất cả bài trong khoảng ngày [min_date, today], dừng khi toàn bộ bài trên page đều cũ hơn min_date.
    Sử dụng requests + BeautifulSoup, không dùng Selenium.
    """
    links = []
    today = datetime.now(timezone.utc).date()
    if min_date is None:
        min_date = today - timedelta(days=10)
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
        all_older = True
        for card in soup.find_all('div', class_='wp-block-techcrunch-card'):
            content = card.find('div', class_='loop-card__content')
            if content:
                h3 = content.find('h3', class_='loop-card__title')
                if h3:
                    a_tag = h3.find('a', class_='loop-card__title-link', href=True)
                    if a_tag:
                        url = a_tag['href']
                        time_tag = content.find('time')
                        if time_tag and time_tag.has_attr('datetime'):
                            try:
                                pub_date = datetime.fromisoformat(time_tag['datetime'].replace('Z', '+00:00')).date()
                            except Exception:
                                pub_date = today
                        else:
                            pub_date = today
                        if min_date <= pub_date <= today:
                            links.append((url, pub_date.isoformat()))
                            all_older = False
        if all_older:
            break
    return links


def extract_article_detail(url):
    resp = requests.get(url, headers=HEADERS, timeout=10)
    soup = BeautifulSoup(resp.text, 'html.parser')
    # Tiêu đề
    title_tag = soup.find('h1')
    title = title_tag.get_text(strip=True) if title_tag else ""
    # Nội dung
    content_div = soup.find('div', class_='entry-content')
    article_text = ""
    if content_div:
        paragraphs = content_div.find_all('p')
        article_text = " ".join(p.get_text() for p in paragraphs)
    # Ngày đăng
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


# Google Custom Search API

def google_search(query, num=10):
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "q": query,
        "key": GOOGLE_CSE_API_KEY,
        "cx": GOOGLE_CSE_ID,
        "num": num
    }
    resp = requests.get(url, params=params)
    data = resp.json()
    print(f"[DEBUG][GOOGLE API RAW] Query: {query} | Items: {[item.get('link','') for item in data.get('items', [])]}")
    return data.get("items", [])

def search_company_website_google(company_name, context=""):
    query = f"{company_name} official website"
    if context:
        query += f" {context}"
    results = google_search(query, num=5)
    for r in results:
        link = r.get("link", "")
        if link and validators.url(link):
            return link
    return ""

def search_company_linkedin_google(company_name, context=""):
    query = f"{company_name} linkedin"
    if context:
        query += f" {context}"
    results = google_search(query, num=5)
    for r in results:
        link = r.get("link", "")
        if "linkedin.com/company" in link and validators.url(link):
            return link
    return ""

def is_valid_url(url):
    return url and url.startswith("http") and validators.url(url)

def verify_company_url_llm(company_name, url, url_type="website", context=""):
    prompt = (
        f"Is '{url}' the official {url_type} of the startup company named '{company_name}'"
        f"{f', {context}' if context else ''}? Answer only Yes or No."
    )
    print(f"[DEBUG] LLM VERIFY PROMPT: {prompt}")
    response = openai.chat.completions.create(
        model=config.LLM_MODEL_ID,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4,
        temperature=0
    )
    answer = response.choices[0].message.content.strip().lower()
    print(f"[DEBUG] LLM VERIFY RESPONSE: {answer}")
    return answer.startswith("yes")

# Bỏ xác thực lại bằng LLM cho SerpAPI, chỉ lấy kết quả đầu tiên hợp lệ

def find_company_website_llm(company_name, context=""):
    prompt = (
        f"What is the official website of the startup company named '{company_name}'{f', {context}' if context else ''}? Only return the URL, nothing else."
    )
    response = openai.chat.completions.create(
        model=config.LLM_MODEL_ID,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=32,
        temperature=0
    )
    url = response.choices[0].message.content.strip()
    if is_valid_url(url):
        return url
    # Nếu LLM trả về không hợp lệ, dùng SerpAPI (không xác thực lại)
    url = search_company_website_google(company_name, context)
    return url or ""


def find_company_linkedin_llm(company_name, context="", website=None):
    prompt = (
        f"What is the LinkedIn page URL of the startup company named '{company_name}'{f', {context}' if context else ''}? Only return the URL, nothing else."
    )
    response = openai.chat.completions.create(
        model=config.LLM_MODEL_ID,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=32,
        temperature=0
    )
    url = response.choices[0].message.content.strip()
    if is_valid_url(url) and "linkedin.com/company" in url:
        return url
    # Nếu LLM trả về không hợp lệ, dùng SerpAPI (không xác thực lại)
    url = search_company_linkedin_google(company_name, context)
    return url or ""


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
        # Loại trừ các bài báo về IPO
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


# Tối ưu prompt LLM cho is_funding_article_llm

def is_funding_article_llm(article_text, debug=False):
    prompt = (
        "Given the following news article, answer only Yes or No: "
        "Is this article PRIMARILY about a company that has JUST SUCCESSFULLY raised new funds (funding, investment, venture round, seed, series A/B/C, etc) for its future development or growth? "
        "Do NOT answer Yes if the article is mainly about bankruptcy, fraud, lawsuits, indictments, liquidation, company shutdown, or past funding events. "
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
    prompt = (
        "Given the following news article about a company raising funds, extract:\n"
        "- The company name\n"
        "- The official website URL\n"
        "- The LinkedIn page URL\n"
        "- The date the company raised funds (if available, in YYYY-MM-DD format, else empty)\n"
        "Return the result as JSON with keys: company_name, website, linkedin, raised_date. Only return valid JSON, nothing else.\n\n"
        f"Article:\n{article_text}\n\nJSON:"
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


def extract_company_info(article_url):
    """
    Extract company name, website, and date from a TechCrunch article.
    """
    try:
        resp = requests.get(article_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        # Lấy nội dung bài báo
        article_body = soup.find('div', class_='entry-content')
        article_text = ""
        if article_body:
            paragraphs = article_body.find_all('p')
            article_text = " ".join(p.get_text() for p in paragraphs[:3])  # Lấy 3 đoạn đầu
        # Gọi LLM để trích xuất tên công ty
        company_name = extract_company_name_llm(article_text)
        # Gọi LLM để tìm website và LinkedIn
        website = find_company_website_llm(company_name)
        linkedin = find_company_linkedin_llm(company_name)
        # Lấy ngày đăng bài
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
            'source': 'TechCrunch'
        }
    except Exception as e:
        print(f"Error extracting {article_url}: {e}")
        return None


# Tối ưu loại trùng lặp khi lưu vào CSV

def normalize_company_name(name):
    """
    Chuẩn hóa tên công ty: bỏ Inc, Ltd, Corp, dấu câu, viết thường, bỏ khoảng trắng.
    """
    if not name:
        return ''
    name = name.lower()
    name = re.sub(r'\b(inc|ltd|corp|co|corporation|limited|llc|plc|inc\.|ltd\.|corp\.|co\.|s\.a\.|s\.p\.a\.|gmbh|ag|bv|oy|ab|sas|sa|pte|pte\.|group|holdings|holding|company|companies)\b', '', name)
    name = re.sub(r'[^a-z0-9]', '', name)  # Bỏ dấu câu, khoảng trắng
    return name.strip()

def load_existing_entries():
    """
    Load existing entries from CSV to avoid duplicates.
    Chuẩn hóa tên công ty khi loại trùng.
    """
    entries = set()
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = (normalize_company_name(row.get('company_name', '')), row.get('article_url', '').strip())
                entries.add(key)
    return entries


def save_to_csv(data):
    """
    Save a list of dicts to CSV, appending if file exists.
    """
    file_exists = os.path.exists(CSV_FILE)
    with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['raised_date', 'company_name', 'website', 'linkedin', 'article_url', 'source', 'crawl_date'])
        if not file_exists:
            writer.writeheader()
        for row in data:
            writer.writerow(row)


def find_company_website(company_name, context=""):
    url = find_company_website_llm(company_name, context)
    if is_valid_url(url):
        return url
    url = search_company_website_google(company_name, context)
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
    return search_company_linkedin_google(company_name, context)


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
    results = google_search(query, num=5)
    tried_links = []
    for r in results:
        url = r.get("link", "")
        if url and validators.url(url):
            is_valid = llm_verify_url(company_name, url, "website", news_context)
            tried_links.append((url, is_valid))
            if is_valid:
                return url
    print(f"[DEBUG][NO VALID WEBSITE] {company_name} | Tried: {[l for l, v in tried_links]} | LLM: {[v for l, v in tried_links]}")
    return ""

def search_and_verify_linkedin(company_name, news_context):
    query = f"{company_name} linkedin {news_context}" if news_context else f"{company_name} linkedin"
    results = google_search(query, num=5)
    tried_links = []
    for r in results:
        url = r.get("link", "")
        if "linkedin.com/company" in url and validators.url(url):
            is_valid = llm_verify_url(company_name, url, "LinkedIn", news_context)
            tried_links.append((url, is_valid))
            if is_valid:
                return url
    print(f"[DEBUG][NO VALID LINKEDIN] {company_name} | Tried: {[l for l, v in tried_links]} | LLM: {[v for l, v in tried_links]}")
    return ""

def search_google_website(company_name):
    queries = [
        f"{company_name} official website",
        f"{company_name} ai official website",
        f"{company_name} dev official website",
        f"{company_name} tech official website",
        f"{company_name} inc official website",
        f"{company_name} corp official website",
        f"{company_name} startup official website",
    ]
    company_key = normalize_company_name(company_name)
    allowed_exts = [".com", ".io", ".ai", ".dev", ".app", ".net", ".co", ".org"]
    tried_links = []
    for query in queries:
        try:
            results = list(google_search_lib(query, num_results=10, lang="en"))
            print(f"[DEBUG][GOOGLESEARCH] {company_name} | Query: {query} | Results: {results}")
            for url in results:
                if url and any(ext in url for ext in allowed_exts):
                    if not any(s in url for s in ["linkedin.com", "facebook.com", "twitter.com", "techcrunch.com", "crunchbase.com", "news.", "/news/"]):
                        domain = url.split('//')[-1].split('/')[0].split('.')[0]
                        tried_links.append(url)
                        # Chỉ nhận nếu domain chứa tên công ty đã chuẩn hóa
                        if company_key in domain.replace('-', '').replace('_', ''):
                            print(f"[DEBUG][WEBSITE PICKED] {company_name} | {url}")
                            return url
            # Nếu không có domain phù hợp, bỏ qua
        except Exception as e:
            print(f"[ERROR][GOOGLESEARCH] {company_name} | {query} | {e}")
    if tried_links:
        print(f"[DEBUG][NO STRONG WEBSITE] {company_name} | Tried: {tried_links}")
    return ""

def search_google_linkedin(company_name, website=None):
    queries = [
        f"{company_name} linkedin",
        f"{company_name} ai linkedin",
        f"{company_name} dev linkedin",
        f"{company_name} tech linkedin",
        f"{company_name} inc linkedin",
        f"{company_name} corp linkedin",
    ]
    if website:
        domain = website.split('//')[-1].split('/')[0]
        queries.append(f"{domain} linkedin")
    company_key = normalize_company_name(company_name)
    tried_links = []
    for query in queries:
        try:
            results = list(google_search_lib(query, num_results=10, lang="en"))
            print(f"[DEBUG][GOOGLESEARCH LINKEDIN] {company_name} | Query: {query} | Results: {results}")
            candidates = [url for url in results if "linkedin.com/company" in url]
            for url in candidates:
                tried_links.append(url)
                # Chỉ nhận nếu slug linkedin chứa tên công ty đã chuẩn hóa
                slug = url.split("linkedin.com/company/")[-1].split("/")[0].replace('-', '').replace('_', '').lower()
                if company_key in slug:
                    print(f"[DEBUG][LINKEDIN PICKED (company)] {company_name} | {url}")
                    return url
            # Nếu không có slug phù hợp, bỏ qua
        except Exception as e:
            print(f"[ERROR][GOOGLESEARCH LINKEDIN] {company_name} | {query} | {e}")
    if tried_links:
        print(f"[DEBUG][NO STRONG LINKEDIN] {company_name} | Tried: {tried_links}")
    return ""

def verify_and_normalize_link(company_name, link, link_type='website'):
    """
    Xác thực và chuẩn hóa link website/LinkedIn cho công ty.
    - company_name: tên công ty gốc
    - link: link website hoặc LinkedIn cần xác thực
    - link_type: 'website' hoặc 'linkedin'
    Trả về link nếu hợp lệ, ngược lại trả về rỗng.
    """
    if not link or not isinstance(link, str):
        return ""
    norm_name = normalize_company_name(company_name)
    if link_type == 'website':
        try:
            domain = link.split('//')[-1].split('/')[0].split('.')[0]
            domain_norm = domain.replace('-', '').replace('_', '').lower()
            if norm_name in domain_norm:
                return link
        except Exception:
            pass
        return ""
    elif link_type == 'linkedin':
        try:
            if "linkedin.com/company/" in link:
                slug = link.split("linkedin.com/company/")[-1].split("/")[0].replace('-', '').replace('_', '').lower()
                if norm_name in slug:
                    return link
        except Exception:
            pass
        return ""
    return ""

def main():
    print('Crawling TechCrunch Startups (last 10 days)...')
    today = date.today()
    min_date = today - timedelta(days=10)
    article_links = get_article_links_last_7_days(min_date=min_date, max_pages=5)
    print(f'Found {len(article_links)} articles.')
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
            # Log các bài bị skip do không phải bài raise fund
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
                website = verify_and_normalize_link(company_name, website, link_type='website')
                if not website:
                    print(f"[WARNING][NO WEBSITE] {company_name} | {pub_date} | {url}")
                linkedin = search_google_linkedin(company_name, website=website)
                linkedin = verify_and_normalize_link(company_name, linkedin, link_type='linkedin')
                if not linkedin:
                    print(f"[WARNING][NO LINKEDIN] {company_name} | {pub_date} | {url}")
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
    new_entries = list(unique_entries.values())
    if new_entries:
        save_to_csv(new_entries)
        print(f'Saved {len(new_entries)} new entries.')
    else:
        print('No new entries found.')


if __name__ == '__main__':
    main()