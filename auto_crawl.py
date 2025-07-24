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
    print('[WARNING] thefuzz chưa được cài đặt. Hãy chạy: pip install thefuzz')
    fuzz = None

import pandas as pd
from extractors import (
    extract_article_detail, extract_company_name_and_raised_date_llm, extract_funding_info_llm,
    extract_finsmes_article_detail, is_funding_article_llm, extract_possible_company_website, is_negative_news
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
        min_date = today - timedelta(days=7)
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
        return url, False  # False = không mơ hồ
    if url.lower() != 'unknown':
        print(f"[DEBUG][LLM WEBSITE GUESS] {company_name} | {url}")
        return url, True  # True = mơ hồ
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
    # 1. Tách đoạn chứa entity
    candidate_text = extract_candidate_paragraphs(article_text)
    # 2. Prompt rõ ràng
    prompt = (
        "Hãy trích xuất thông tin sau từ đoạn văn:\n"
        "1. Tên công ty được thành lập mới hoặc vừa gọi vốn\n"
        "2. Website chính thức (nếu không có trong đoạn, hãy để trống)\n"
        "3. Link LinkedIn của công ty (nếu không có trong đoạn, hãy để trống)\n"
        "4. Ngày công ty gọi vốn (nếu có, định dạng YYYY-MM-DD, nếu không có thì để trống)\n"
        "Kết quả trả về ở định dạng JSON với các key: company_name, website, linkedin, raised_date.\n"
        "Chỉ trả về JSON, không giải thích gì thêm.\n\n"
        f"Đoạn văn:\n{candidate_text}\n\nJSON:"
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
    # 3. Fallback search nếu thiếu website/linkedin
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
        info = extract_funding_info_llm(article_text)
        company_name = info.get("company_name", "") if info else ""
        website = info.get("website", "") if info else ""
        linkedin = info.get("linkedin", "") if info else ""
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
    Chuẩn hóa tên công ty: bỏ hậu tố phổ biến, dấu câu, viết thường, bỏ khoảng trắng, loại từ phổ biến.
    """
    if not name:
        return ''
    name = name.lower()
    # Loại bỏ các hậu tố phổ biến
    blacklist = [
        'inc', 'ltd', 'corp', 'co', 'corporation', 'limited', 'llc', 'plc', 'group', 'holdings', 'holding', 'company', 'companies',
        'sas', 'sa', 'pte', 'group', 'ventures', 'ai', 'robotics', 'systems', 'solutions', 'partners', 'capital',
        'inc.', 'ltd.', 'corp.', 'co.', 'group.', 'ventures.', 'ai.', 'robotics.', 'systems.', 'solutions.', 'partners.', 'capital.', 'holdings.', 'company.', 'co.', 'llc.', 'plc.', 'limited.', 'ltd.'
    ]
    for word in blacklist:
        name = re.sub(r'\b' + word + r'\b', '', name)
    name = re.sub(r'[^a-z0-9]', '', name)  # Bỏ dấu câu, khoảng trắng
    return name.strip()

def normalize_amount(amount):
    # Chuẩn hóa số tiền funding về dạng số (float, triệu USD)
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
    # Mặc định là triệu USD
    return round(val, 2)

def normalize_date(date_str):
    if not date_str:
        return ''
    import re
    date_str = str(date_str).strip()
    # Nếu đã đúng format yyyy-mm-dd
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').strftime('%Y-%m-%d')
    except:
        pass
    # Nếu dạng July 22, 2025
    try:
        return datetime.strptime(date_str, '%B %d, %Y').strftime('%Y-%m-%d')
    except:
        pass
    # Nếu dạng "July 22,2025" (thiếu space)
    try:
        return datetime.strptime(date_str.replace(',', ', '), '%B %d, %Y').strftime('%Y-%m-%d')
    except:
        pass
    # Nếu dạng "22 July 2025"
    try:
        return datetime.strptime(date_str, '%d %B %Y').strftime('%Y-%m-%d')
    except:
        pass
    # Nếu dạng "2025/07/22"
    try:
        return datetime.strptime(date_str, '%Y/%m/%d').strftime('%Y-%m-%d')
    except:
        pass
    # Nếu dạng "2025.07.22"
    try:
        return datetime.strptime(date_str, '%Y.%m.%d').strftime('%Y-%m-%d')
    except:
        pass
    # Nếu dạng "22/07/2025"
    try:
        return datetime.strptime(date_str, '%d/%m/%Y').strftime('%Y-%m-%d')
    except:
        pass
    # Nếu dạng "22.07.2025"
    try:
        return datetime.strptime(date_str, '%d.%m.%Y').strftime('%Y-%m-%d')
    except:
        pass
    # Nếu không parse được thì trả về chuỗi gốc
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
    # Loại trùng theo (company, date, amount) ưu tiên TechCrunch, nếu amount thiếu thì chỉ so sánh (company, date)
    seen = OrderedDict()
    for row in rows:
        name = normalize_company_name(row.get('company_name', ''))
        date = normalize_date(row.get('raised_date', ''))
        amount = normalize_amount(row.get('amount', ''))
        key_full = (name, date, amount)
        key_noval = (name, date)
        # Nếu đã có bản ghi TechCrunch cùng key, bỏ qua bản ghi mới
        if amount is not None:
            if key_full in seen:
                # Ưu tiên TechCrunch
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
    # Ghi lại file
    with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in seen.values():
            writer.writerow(row)

# Sửa lại hàm load_existing_entries

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
    Trước khi lưu, loại trùng bằng pandas theo ['company_name', 'article_url'].
    """
    import csv
    import os
    import pandas as pd
    fieldnames = ['raised_date', 'company_name', 'website', 'linkedin', 'article_url', 'source', 'amount', 'industry', 'crawl_date']
    file_exists = os.path.exists(CSV_FILE)
    # Lưu tạm ra file
    temp_file = CSV_FILE + ".tmp"
    with open(temp_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in entries:
            writer.writerow(row)
    # Đọc lại bằng pandas và loại trùng
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

# Đảm bảo hàm crawl_finsmes_usa tồn tại
# (Nếu đã có ở trên file thì bỏ qua đoạn này)
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

# Thêm delay vào search_google_website và search_google_linkedin
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
    min_date = today - timedelta(days=7)
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
    min_date = today - timedelta(days=7)
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