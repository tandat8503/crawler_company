import sys
import os
from datetime import datetime, timezone, date, timedelta
import random
import requests
from bs4 import BeautifulSoup

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
    verify_and_normalize_link,
    crawl_finsmes_usa,
    extract_finsmes_article_detail
)

CSV_FILE = os.path.join(os.path.dirname(__file__), 'companies.csv')

print("[INFO] Google search sẽ sleep ngẫu nhiên 10-20s giữa các request để giảm block!")

def crawl_techcrunch_today():
    print('Crawling TechCrunch Startups (today only)...')
    today = date.today()
    article_links = get_article_links_last_7_days(min_date=today, max_pages=3)
    print(f'Found {len(article_links)} TechCrunch articles.')
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
    return list(unique_entries.values())

def crawl_finsmes_today():
    print('Crawling Finsmes (today only)...')
    today = date.today()
    finsmes_articles = crawl_finsmes_usa(max_pages=3)
    print(f'Found {len(finsmes_articles)} Finsmes articles.')
    existing_entries = load_existing_entries()
    unique_entries = {}
    for a in finsmes_articles:
        url = a['url']
        pub_date = a['pub_date']
        if pub_date != today.strftime('%B %d, %Y') and pub_date != today.isoformat():
            continue
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
    return list(unique_entries.values())

def crawl_all_today():
    today = date.today()
    all_entries = []
    # TechCrunch
    tech_entries = crawl_techcrunch_today()
    if tech_entries:
        save_to_csv(tech_entries)
        print(f'Saved {len(tech_entries)} TechCrunch entries.')
        all_entries.extend(tech_entries)
    else:
        print('No new TechCrunch entries found.')
        # Ghi chú vào CSV nếu không có tin mới
        with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
            from csv import writer
            w = writer(f)
            w.writerow([
                today.isoformat(), # raised_date
                '---',    # company_name
                '',       # website
                '',       # linkedin
                '',       # article_url
                'NO_NEWS_TECHCRUNCH',# source
                today.isoformat(),# crawl_date
                f'Không có tin mới TechCrunch ngày {today.isoformat()}' # thông báo
            ])
    # Finsmes
    finsmes_entries = crawl_finsmes_today()
    if finsmes_entries:
        save_to_csv(finsmes_entries)
        print(f'Saved {len(finsmes_entries)} Finsmes entries.')
        all_entries.extend(finsmes_entries)
    else:
        print('No new Finsmes entries found.')
        with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
            from csv import writer
            w = writer(f)
            w.writerow([
                today.isoformat(), # raised_date
                '---',    # company_name
                '',       # website
                '',       # linkedin
                '',       # article_url
                'NO_NEWS_FINSMES',# source
                today.isoformat(),# crawl_date
                f'Không có tin mới Finsmes ngày {today.isoformat()}' # thông báo
            ])
    # Loại trùng lặp
    from auto_crawl import deduplicate_csv
    deduplicate_csv()
    print("Done. Check companies.csv for results.")

if __name__ == '__main__':
    crawl_all_today() 