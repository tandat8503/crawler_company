import sys
import os
from datetime import datetime, timezone, date

# Đảm bảo import được các hàm từ auto_crawl.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from auto_crawl import (
    get_article_links_last_7_days,
    load_existing_entries,
    save_to_csv,
    extract_company_name_and_raised_date_llm,
    is_funding_article_llm,
    search_google_website,
    search_google_linkedin,
    normalize_company_name,
    verify_and_normalize_link
)
import requests
from bs4 import BeautifulSoup

CSV_FILE = os.path.join(os.path.dirname(__file__), 'companies.csv')


def crawl_today():
    print('Crawling TechCrunch Startups (today only)...')
    today = date.today()
    article_links = get_article_links_last_7_days(min_date=today, max_pages=3)
    print(f'Found {len(article_links)} articles.')
    existing_entries = load_existing_entries()
    unique_entries = {}
    for url, pub_date in article_links:
        if pub_date != today.isoformat():
            continue
        source = "TechCrunch"
        try:
            resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; CompanyFundBot/1.0)'}, timeout=10)
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
            info = extract_company_name_and_raised_date_llm(article_text, today.isoformat(), today.isoformat())
            if isinstance(info, list):
                infos = info
            else:
                infos = [info]
            for company_info in infos:
                company_name = company_info.get('company_name', '').strip()
                raised_date = company_info.get('raised_date', '').strip() or pub_date
                norm_name = normalize_company_name(company_name)
                key = (norm_name, url)
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
        # Ghi chú vào CSV để người dùng biết hôm nay không có tin mới
        today_str = today.isoformat()
        with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
            from csv import writer
            w = writer(f)
            w.writerow([
                today_str, # raised_date
                '---',    # company_name
                '',       # website
                '',       # linkedin
                '',       # article_url
                'NO_NEWS',# source
                today_str,# crawl_date
                f'Không có tin mới ngày {today_str}' # thông báo
            ])

if __name__ == '__main__':
    crawl_today() 