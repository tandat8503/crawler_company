import requests
from bs4 import BeautifulSoup
from datetime import datetime
import openai
import config
import re
import json

def extract_article_detail(url):
    resp = requests.get(url, headers=config.HEADERS, timeout=10)
    soup = BeautifulSoup(resp.text, 'html.parser')
    title_tag = soup.find('h1')
    title = title_tag.get_text(strip=True) if title_tag else ""
    content_div = soup.find('div', class_='entry-content')
    article_text = ""
    if content_div:
        paragraphs = content_div.find_all('p')
        article_text = " ".join(p.get_text() for p in paragraphs)
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
        "url": url,
        "soup": soup
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

def extract_finsmes_article_detail(article_url):
    try:
        resp = requests.get(article_url, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        content_div = soup.find("div", class_="td-post-content") or soup.find("div", class_="vc_column_container")
        article_text = ""
        if content_div:
            paragraphs = content_div.find_all("p")
            article_text = " ".join(p.get_text() for p in paragraphs)
        return soup, article_text
    except Exception as e:
        print(f"[ERROR][Finsmes Detail] {article_url}: {e}")
        return None, ""

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

def extract_possible_company_website(soup, company_name):
    norm_name = company_name.lower().replace(' ', '')
    for a in soup.find_all('a', href=True):
        text = a.get_text(strip=True)
        href = a['href']
        if norm_name and norm_name in text.lower().replace(' ', ''):
            if not any(x in href for x in ['techcrunch.com', 'linkedin.com', 'facebook.com', 'twitter.com', 'crunchbase.com', 'news.', '/news/']):
                return href
    return ""

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
        # IPO-related
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