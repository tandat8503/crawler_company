import re
import csv
from datetime import datetime
import os

import config
from db import get_all_companies
from utils.logger import logger

def normalize_company_name(name):
    """
    Normalize company name - improved version
    
    Args:
        name: Original company name
    
    Returns:
        Normalized company name
    """
    if not name:
        return ''
    
    name = name.lower().strip()
    
    # List of keywords to remove
    blacklist = [
        'inc', 'ltd', 'corp', 'co', 'corporation', 'limited', 'llc', 'plc', 
        'group', 'holdings', 'holding', 'company', 'companies',
        'sas', 'sa', 'pte', 'ventures', 'ai', 'robotics', 'systems', 
        'solutions', 'partners', 'capital', 'technologies', 'tech',
        'inc.', 'ltd.', 'corp.', 'co.', 'group.', 'ventures.', 'ai.', 
        'robotics.', 'systems.', 'solutions.', 'partners.', 'capital.', 
        'holdings.', 'company.', 'llc.', 'plc.', 'limited.', 'ltd.',
        'technologies.', 'tech.'
    ]
    
    # Remove keywords
    for word in blacklist:
        name = re.sub(r'\b' + re.escape(word) + r'\b', '', name)
    
    # Remove special characters and extra whitespace
    name = re.sub(r'[^a-z0-9]', '', name)
    name = name.strip()
    
    return name

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

def load_existing_entries():
    """
    Load existing article URLs from database for early deduplication.
    Returns a SET of article_urls.
    """
    existing_urls = set()
    try:
        rows = get_all_companies()
        for row in rows:
            # Assume get_all_companies returns (article_url,) or (company_name, raised_date, article_url, source)
            if len(row) == 1:
                # If only returning article_url
                existing_urls.add(row[0])
            elif len(row) >= 3:
                # If returning multiple columns, get article_url (usually 3rd column)
                existing_urls.add(row[2])
        logger.info(f"Loaded {len(existing_urls)} existing article URLs for deduplication")
    except Exception as e:
        logger.error(f"Error loading existing entries from DB: {e}")
    return existing_urls

def verify_and_normalize_link(company_name, link, link_type='website'):
    """
    Verify and normalize link based on company name
    """
    if not link or not company_name:
        return link
    
    norm_company = normalize_company_name(company_name)
    domain = re.sub(r'[^a-z0-9]', '', link.lower())
    
    # Simple verification
    if norm_company in domain or domain in norm_company:
        return link
    
    return link