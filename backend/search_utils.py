import requests
import re
from urllib.parse import urlparse
from thefuzz import fuzz
import logging
from typing import List, Dict, Optional

from .config import TAVILY_API_KEY
from .utils.logger import logger
from .utils.retry import exponential_backoff_retry

TAVILY_API_URL = "https://api.tavily.com/search"

# --- Hàm gọi API Tavily tập trung ---
@exponential_backoff_retry(max_retries=3, base_delay=1.0)
def search_tavily(query: str, search_depth: str = "basic", max_results: int = 5) -> List[Dict]:
    """
    Gửi một truy vấn đến Tavily API và trả về danh sách kết quả.
    
    Args:
        query: Truy vấn tìm kiếm
        search_depth: Độ sâu tìm kiếm ("basic" hoặc "advanced")
        max_results: Số kết quả tối đa
    
    Returns:
        List các kết quả từ Tavily
    """
    headers = {"Authorization": f"Bearer {TAVILY_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "query": query,
        "search_depth": search_depth,
        "max_results": max_results
    }
    
    try:
        resp = requests.post(TAVILY_API_URL, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get('results', [])
    except requests.exceptions.RequestException as e:
        logger.error(f"Lỗi khi gọi Tavily API cho query '{query}': {e}")
        return []

# --- Các hàm chuẩn hóa và so khớp ---
def normalize_name_for_matching(name: str) -> str:
    """
    Chuẩn hóa tên để so khớp, loại bỏ các từ chung chung.
    
    Args:
        name: Tên cần chuẩn hóa
    
    Returns:
        Tên đã được chuẩn hóa
    """
    if not name:
        return ''
    
    name = name.lower().strip()
    
    # Loại bỏ các hậu tố và từ chung
    blacklist = [
        'inc', 'ltd', 'corp', 'co', 'llc', 'group', 'holdings', 'ventures', 
        'ai', 'robotics', 'systems', 'solutions', 'partners', 'capital', 
        'technologies', 'labs', 'corporation', 'limited', 'company', 'companies',
        'plc', 'sas', 'sa', 'pte', 'international', 'global', 'worldwide'
    ]
    
    for word in blacklist:
        name = re.sub(r'\b' + re.escape(word) + r'\b', '', name)
    
    # Loại bỏ các ký tự không phải chữ và số
    name = re.sub(r'[^a-z0-9]', '', name)
    return name.strip()

def get_url_match_score(company_name: str, url: str, title: str = "", content: str = "") -> int:
    """
    Chấm điểm mức độ phù hợp của một URL với tên công ty.
    Tận dụng cả URL, tiêu đề và nội dung trang.
    
    Args:
        company_name: Tên công ty
        url: URL cần đánh giá
        title: Tiêu đề trang
        content: Nội dung trang
    
    Returns:
        Điểm từ 0-100
    """
    norm_company = normalize_name_for_matching(company_name)
    
    # Chấm điểm dựa trên URL
    parsed_url = urlparse(url)
    domain = parsed_url.netloc.replace('www.', '')
    norm_domain = normalize_name_for_matching(domain)
    url_score = fuzz.partial_ratio(norm_company, norm_domain)

    # Chấm điểm dựa trên tiêu đề trang
    title_score = 0
    if title:
        norm_title = normalize_name_for_matching(title)
        title_score = fuzz.partial_ratio(norm_company, norm_title)

    # Chấm điểm dựa trên nội dung (nếu có)
    content_score = 0
    if content:
        norm_content = normalize_name_for_matching(content[:500])  # Lấy 500 ký tự đầu
        content_score = fuzz.partial_ratio(norm_company, norm_content)

    # Điểm cuối cùng là điểm cao nhất
    return max(url_score, title_score, content_score)

def is_social_media_or_news_site(url: str) -> bool:
    """
    Kiểm tra xem URL có phải là trang mạng xã hội hoặc tin tức không.
    
    Args:
        url: URL cần kiểm tra
    
    Returns:
        True nếu là trang mạng xã hội/tin tức
    """
    social_news_domains = [
        'linkedin.com', 'twitter.com', 'facebook.com', 'instagram.com',
        'crunchbase.com', 'techcrunch.com', 'finsmes.com', 'reuters.com',
        'bloomberg.com', 'forbes.com', 'wsj.com', 'nytimes.com',
        'medium.com', 'substack.com', 'news.ycombinator.com'
    ]
    
    parsed_url = urlparse(url)
    domain = parsed_url.netloc.lower()
    
    return any(site in domain for site in social_news_domains)

# --- Hàm tìm kiếm chính sử dụng Tavily ---
def find_company_website(company_name: str) -> str:
    """
    Tìm website chính thức của công ty bằng Tavily và logic so khớp thông minh.
    
    Args:
        company_name: Tên công ty cần tìm website
    
    Returns:
        URL website chính thức hoặc chuỗi rỗng nếu không tìm thấy
    """
    if not company_name:
        return ""
    
    # Tạo các query khác nhau để tăng khả năng tìm thấy
    queries = [
        f'official website for "{company_name}"',
        f'"{company_name}" official site',
        f'"{company_name}" homepage',
        f'"{company_name}" company website'
    ]
    
    best_match = {"url": "", "score": 0}
    
    for query in queries:
        results = search_tavily(query, max_results=5)
        
        for item in results:
            url = item.get('url', '')
            title = item.get('title', '')
            content = item.get('content', '')
            
            # Bỏ qua các trang mạng xã hội và tin tức
            if is_social_media_or_news_site(url):
                continue
                
            score = get_url_match_score(company_name, url, title, content)
            
            # Ưu tiên các trang có điểm cao
            if score > best_match["score"]:
                best_match["url"] = url
                best_match["score"] = score
                
        # Nếu đã tìm thấy kết quả tốt, dừng lại
        if best_match["score"] >= 85:
            break
    
    logger.info(f"Tìm website cho '{company_name}': URL tốt nhất '{best_match['url']}' với điểm {best_match['score']}.")
    
    # Chỉ chấp nhận kết quả nếu điểm đủ cao (ngưỡng tin cậy)
    return best_match["url"] if best_match["score"] >= 80 else ""

def find_company_linkedin(company_name: str) -> str:
    """
    Tìm trang LinkedIn chính thức của công ty bằng Tavily.
    
    Args:
        company_name: Tên công ty cần tìm LinkedIn
    
    Returns:
        URL LinkedIn chính thức hoặc chuỗi rỗng nếu không tìm thấy
    """
    if not company_name:
        return ""
        
    # Tạo các query khác nhau cho LinkedIn
    queries = [
        f'"{company_name}" site:linkedin.com/company',
        f'"{company_name}" LinkedIn company page',
        f'"{company_name}" official LinkedIn'
    ]
    
    best_match = {"url": "", "score": 0}

    for query in queries:
        results = search_tavily(query, max_results=3)
        
        for item in results:
            url = item.get('url', '')
            title = item.get('title', '')
            content = item.get('content', '')

            if 'linkedin.com/company' not in url:
                continue
                
            score = get_url_match_score(company_name, url, title, content)
            
            if score > best_match["score"]:
                best_match["url"] = url
                best_match["score"] = score
                
        # Nếu đã tìm thấy kết quả tốt, dừng lại
        if best_match["score"] >= 85:
            break
            
    logger.info(f"Tìm LinkedIn cho '{company_name}': URL tốt nhất '{best_match['url']}' với điểm {best_match['score']}.")
    
    return best_match["url"] if best_match["score"] >= 80 else ""

# --- Hàm tiện ích cho việc xác thực ---
def verify_company_info(company_name: str, website: str = "", linkedin: str = "") -> Dict[str, str]:
    """
    Xác thực và cải thiện thông tin công ty bằng Tavily.
    
    Args:
        company_name: Tên công ty
        website: Website hiện tại (nếu có)
        linkedin: LinkedIn hiện tại (nếu có)
    
    Returns:
        Dict với website và linkedin đã được xác thực
    """
    result = {"website": website, "linkedin": linkedin}
    
    # Nếu chưa có website, tìm mới
    if not website:
        result["website"] = find_company_website(company_name)
    
    # Nếu chưa có LinkedIn, tìm mới
    if not linkedin:
        result["linkedin"] = find_company_linkedin(company_name)
    
    return result

# --- Hàm tương thích ngược (để không phải sửa code cũ ngay) ---
def search_company_website_tavily(company_name: str) -> str:
    """Hàm tương thích ngược - gọi find_company_website"""
    return find_company_website(company_name)

def search_company_linkedin_tavily(company_name: str) -> str:
    """Hàm tương thích ngược - gọi find_company_linkedin"""
    return find_company_linkedin(company_name)

# --- Các hàm cũ đã được loại bỏ ---
# Tất cả các hàm liên quan đến googlesearch-python đã được xóa
# Các hàm cũ như search_google_website, search_google_linkedin, etc. đã bị loại bỏ 