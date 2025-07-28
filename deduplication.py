import re
import os
import csv
from datetime import datetime
from collections import OrderedDict

def normalize_company_name(name):
    if not name:
        return ''
    name = name.lower()
    blacklist = [
        'inc', 'ltd', 'corp', 'co', 'corporation', 'limited', 'llc', 'plc', 'group', 'holdings', 'holding', 'company', 'companies',
        'sas', 'sa', 'pte', 'group', 'ventures', 'ai', 'robotics', 'systems', 'solutions', 'partners', 'capital',
        'inc.', 'ltd.', 'corp.', 'co.', 'group.', 'ventures.', 'ai.', 'robotics.', 'systems.', 'solutions.', 'partners.', 'capital.', 'holdings.', 'company.', 'co.', 'llc.', 'plc.', 'limited.', 'ltd.'
    ]
    for word in blacklist:
        name = re.sub(r'\b' + word + r'\b', '', name)
    name = re.sub(r'[^a-z0-9]', '', name)
    return name.strip()

def normalize_amount(amount):
    if not amount:
        return None
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
    return round(val, 2)

def normalize_date(date_str):
    if not date_str:
        return ''
    date_str = str(date_str).strip()
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').strftime('%Y-%m-%d')
    except:
        pass
    try:
        return datetime.strptime(date_str, '%B %d, %Y').strftime('%Y-%m-%d')
    except:
        pass
    try:
        return datetime.strptime(date_str.replace(',', ', '), '%B %d, %Y').strftime('%Y-%m-%d')
    except:
        pass
    try:
        return datetime.strptime(date_str, '%d %B %Y').strftime('%Y-%m-%d')
    except:
        pass
    try:
        return datetime.strptime(date_str, '%Y/%m/%d').strftime('%Y-%m-%d')
    except:
        pass
    try:
        return datetime.strptime(date_str, '%Y.%m.%d').strftime('%Y-%m-%d')
    except:
        pass
    try:
        return datetime.strptime(date_str, '%d/%m/%Y').strftime('%Y-%m-%d')
    except:
        pass
    try:
        return datetime.strptime(date_str, '%d.%m.%Y').strftime('%Y-%m-%d')
    except:
        pass
    return date_str

def deduplicate_csv(CSV_FILE):
    import pandas as pd
    if not os.path.exists(CSV_FILE):
        return
    fieldnames = ['raised_date', 'company_name', 'website', 'linkedin', 'article_url', 'source', 'amount', 'industry', 'crawl_date']
    df = pd.read_csv(CSV_FILE)
    df = df.drop_duplicates(subset=["company_name", "raised_date", "article_url"], keep="first")
    df.to_csv(CSV_FILE, index=False)
    print(f"[INFO][DEDUP] Saved {len(df)} unique entries to {CSV_FILE}")

def load_existing_entries(CSV_FILE):
    entries = {}
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = (
                    normalize_company_name(row.get('company_name', '')),
                    normalize_date(row.get('raised_date', '')),
                    row.get('article_url', '').strip()
                )
                entries[key] = row.get('source', '')
    return entries

def get_existing_keys(csv_file):
    keys = set()
    if os.path.exists(csv_file):
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = normalize_company_name(row.get('company_name', ''))
                date = normalize_date(row.get('raised_date', ''))
                amount = normalize_amount(row.get('amount', ''))
                key = (name, date, amount)
                keys.add(key)
    return keys

def verify_and_normalize_link(company_name, link, link_type='website'):
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