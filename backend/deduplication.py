import re
import os
import csv
from datetime import datetime
from collections import OrderedDict
from .db import get_all_companies
from .utils.logger import logger

def normalize_company_name(name):
    """
    Chuẩn hóa tên công ty - phiên bản cải tiến
    
    Args:
        name: Tên công ty gốc
    
    Returns:
        Tên công ty đã được chuẩn hóa
    """
    if not name:
        return ''
    
    name = name.lower().strip()
    
    # Danh sách từ khóa cần loại bỏ
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
    
    # Loại bỏ các từ khóa
    for word in blacklist:
        name = re.sub(r'\b' + re.escape(word) + r'\b', '', name)
    
    # Loại bỏ ký tự đặc biệt và khoảng trắng thừa
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
    Tải các bản ghi hiện có từ database để loại bỏ trùng lặp.
    Trả về một tập hợp các bộ ba (tên_công_ty_chuẩn_hóa, ngày_gọi_vốn_chuẩn_hóa, url_bài_viết).
    """
    existing_keys = set()
    try:
        rows = get_all_companies()
        for row in rows:
            company_name, raised_date, article_url, source = row
            normalized_name = normalize_company_name(company_name)
            normalized_date_str = normalize_date(raised_date)
            existing_keys.add((normalized_name, normalized_date_str, article_url))
        logger.info(f"Loaded {len(existing_keys)} existing entries for deduplication")
    except Exception as e:
        logger.error(f"Error loading existing entries from DB: {e}")
    return existing_keys

def verify_and_normalize_link(company_name, link, link_type='website'):
    """
    Verify và normalize link dựa trên tên công ty
    """
    if not link or not company_name:
        return link
    
    norm_company = normalize_company_name(company_name)
    domain = re.sub(r'[^a-z0-9]', '', link.lower())
    
    # Simple verification
    if norm_company in domain or domain in norm_company:
        return link
    
    return link