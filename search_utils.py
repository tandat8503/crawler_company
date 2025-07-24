import requests
from bs4 import BeautifulSoup
from thefuzz import fuzz
import re
from googlesearch import search as google_search_lib
from openai import ChatCompletion
import config
import time
from urllib.parse import urlparse
import openai
import random

def normalize_name(name):
    import re
    name = name.lower().strip()
    name = re.sub(r"(inc\\.?|technologies?|labs|ai|dev|systems?|group|corp|llc|ltd|co|company|partners|ventures|capital|solutions|robotics|holdings|plc|sas|sa|pte)$", "", name)
    name = re.sub(r"[^a-z0-9]", "", name)
    return name.strip()

COMPANY_DOMAIN_WHITELIST = {
    "runetechnologies": {
        "website": "https://www.runetech.co/",
        "linkedin": "https://www.linkedin.com/company/runetech/"
    },
    # Bổ sung các công ty khác nếu cần
}

def get_whitelisted_links(company_name):
    norm_name = normalize_name(company_name)
    return COMPANY_DOMAIN_WHITELIST.get(norm_name, {})

def safe_google_search(query, num_results=5):
    """
    Wrapper cho googlesearch search với sleep ngẫu nhiên 5-10s giữa các request để giảm nguy cơ bị Google block.
    """
    results = []
    try:
        for url in google_search_lib(query, num_results=num_results):
            results.append(url)
            sleep_time = random.uniform(4,8)
            print(f"[SAFE SEARCH] Sleep {sleep_time:.1f}s sau mỗi kết quả Google...")
            time.sleep(sleep_time)
    except Exception as e:
        print(f"[ERROR][SAFE GOOGLE SEARCH] {query} | {e}")
    return results

def search_google_website(company_name):
    normalized = normalize_name(company_name)
    queries = [
        f"{company_name} official site",
        f"{company_name} ai",
        f"{company_name} dev",
        f"{company_name} technologies"
    ]
    for query in queries:
        found = False
        try:
            for url in safe_google_search(query, num_results=5):
                domain = urlparse(url).netloc
                slug = domain.split(".")[0]
                score = fuzz.partial_ratio(slug.lower(), normalized)
                if score >= 80:
                    print(f"[GOOGLE][WEBSITE][MATCH] {company_name} | Query: {query} | URL: {url} | slug: {slug} | norm: {normalized} | score: {score}")
                    return url
                else:
                    print(f"[GOOGLE][WEBSITE][NO MATCH] {company_name} | Query: {query} | URL: {url} | slug: {slug} | norm: {normalized} | score: {score}")
        except Exception as e:
            print(f"[ERROR][GOOGLESEARCH] {company_name} | Query: {query} | {e}")
            if '429' in str(e):
                print('[GOOGLE][BLOCKED] Google đang chặn, hãy thử lại sau hoặc tăng thời gian sleep!')
        print(f"[GOOGLE][WEBSITE][NO RESULT] {company_name} | Query: {query}")
    print(f"[GOOGLE][WEBSITE][FAIL] {company_name} | Không tìm được website phù hợp.")
    return ""

def search_google_linkedin(company_name, website=None):
    normalized = normalize_name(company_name)
    query = f"{company_name} site:linkedin.com/company"
    found = False
    try:
        for url in safe_google_search(query, num_results=5):
            if "linkedin.com/company" in url:
                slug = url.split("/")[-1]
                score = fuzz.partial_ratio(slug.lower(), normalized)
                if score >= 80:
                    print(f"[GOOGLE][LINKEDIN][MATCH] {company_name} | URL: {url} | slug: {slug} | norm: {normalized} | score: {score}")
                    return url
                else:
                    print(f"[GOOGLE][LINKEDIN][NO MATCH] {company_name} | URL: {url} | slug: {slug} | norm: {normalized} | score: {score}")
    except Exception as e:
        print(f"[ERROR][GOOGLESEARCH LINKEDIN] {company_name} | Query: {query} | {e}")
        if '429' in str(e):
            print('[GOOGLE][BLOCKED] Google đang chặn, hãy thử lại sau hoặc tăng thời gian sleep!')
    print(f"[GOOGLE][LINKEDIN][FAIL] {company_name} | Không tìm được LinkedIn phù hợp.")
    return ""

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
    if url.startswith('http'):
        return url, False
    if url.lower() != 'unknown':
        return url, True
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
    if url.startswith('http') and "linkedin.com/company" in url:
        return url, False
    if url.lower() != 'unknown':
        return url, True
    return '', True

def verify_link_with_google(link, company_name, is_linkedin=False):
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
            for url in safe_google_search(query, num_results=5):
                domain = urlparse(url).netloc
                slug = domain.split(".")[0]
                score = fuzz.partial_ratio(slug.lower(), normalized)
                if link.replace('LLM_guess: ', '').strip().lower() in url.strip().lower() or url.strip().lower() in link.replace('LLM_guess: ', '').strip().lower():
                    if score >= 80:
                        print(f"[GOOGLE][VERIFY][MATCH] {company_name} | Query: {query} | URL: {url} | score: {score}")
                        return True
        except Exception as e:
            print(f"[ERROR][GOOGLESEARCH VERIFY] {company_name} | Query: {query} | {e}")
            if '429' in str(e):
                print('[GOOGLE][BLOCKED] Google đang chặn, hãy thử lại sau hoặc tăng thời gian sleep!')
    print(f"[GOOGLE][VERIFY][FAIL] {company_name} | Không xác thực được link qua Google.")
    return False 

def search_company_links(company_name, type='website', top_k=5):
    """
    Tìm top_k link website hoặc linkedin cho công ty, trả về list [(url, score, title, reason)]
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
            links = safe_google_search(query, num_results=top_k)
            for url in links:
                if type == 'website' and any(ext in url for ext in ['.com', '.ai', '.io', '.co', '.net', '.org', '.dev', '.app']):
                    results.append(url)
                elif type == 'linkedin' and site_filter and site_filter in url:
                    results.append(url)
        except Exception as e:
            print(f"[ERROR][GOOGLESEARCH COMPANY LINKS] {company_name} | Query: {query} | {e}")
            if '429' in str(e):
                print('[GOOGLE][BLOCKED] Google đang chặn, hãy thử lại sau hoặc tăng thời gian sleep!')
            continue
        if len(results) >= top_k:
            break
    # Loại trùng
    results = list(dict.fromkeys(results))[:top_k]
    scored = []
    for url in results:
        ok, score, title, reason = verify_link_match(company_name, url, type)
        scored.append((url, score, title, reason))
    return scored

def verify_link_match(company_name, url, type='website'):
    """
    Xác thực link dựa trên domain, title, meta, slug. Trả về (True/False, score, title, reason)
    """
    try:
        resp = requests.get(url, timeout=7)
        html = resp.text
        title = ''
        meta_desc = ''
        og_title = ''
        # Lấy title
        m = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
        if m:
            title = m.group(1)
        # Lấy meta description
        m = re.search(r'<meta name=["\']description["\'] content=["\'](.*?)["\']', html, re.IGNORECASE)
        if m:
            meta_desc = m.group(1)
        # Lấy og:title
        m = re.search(r'<meta property=["\']og:title["\'] content=["\'](.*?)["\']', html, re.IGNORECASE)
        if m:
            og_title = m.group(1)
        # So khớp domain
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
        # Heuristic: >=2 yếu tố > 70 là hợp lệ
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
    Trả về link tốt nhất (website/linkedin) cho công ty, có thể dùng LLM rerank nếu cần.
    """
    scored = search_company_links(company_name, type=type, top_k=5)
    # Nếu không dùng LLM rerank, lấy link có score cao nhất và pass xác thực
    best = None
    best_score = 0
    for url, score, title, reason in scored:
        if score > best_score and 'Pass' in reason:
            best = url
            best_score = score
    if best or not use_llm:
        return best
    # Nếu muốn dùng LLM rerank (khi không có link pass hoặc muốn chắc chắn hơn)
    if use_llm and scored:
        prompt = f"""
Given the company name '{company_name}', choose the correct {type} from the following list:\n"""
        for i, (url, score, title, reason) in enumerate(scored, 1):
            prompt += f"{i}. {url} (title: {title})\n"
        prompt += "\nReturn only the number of the best match."
        response = ChatCompletion.create(
            model=config.LLM_MODEL_ID,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4,
            temperature=0
        )
        content = response.choices[0].message.content.strip()
        try:
            idx = int(content)
            if 1 <= idx <= len(scored):
                return scored[idx-1][0]
        except Exception:
            pass
    return None 