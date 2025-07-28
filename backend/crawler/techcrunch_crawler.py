import requests
from bs4 import BeautifulSoup
import re
import logging
from datetime import datetime, timedelta, date, timezone
from urllib.parse import urlparse

try:
    from thefuzz import fuzz
except ImportError:
    logging.warning('[WARNING] thefuzz không được cài đặt. Vui lòng chạy: pip install thefuzz')
    fuzz = None

from .. import config
from ..deduplication import (
    normalize_company_name, load_existing_entries, normalize_date
)
from ..search_utils import (
    find_company_website, find_company_linkedin, verify_company_info
)
from ..llm_utils import (
    extract_company_name_and_raised_date_llm, is_funding_article_llm, 
    extract_company_info_llm, normalize_domain, company_name_matches_domain,
    llm_prompt, safe_parse_json
)
from ..utils.logger import logger

def normalize_name(name):
    return re.sub(r'[^a-z0-9]', '', name.lower())

def extract_domain_slug(url):
    parsed = urlparse(url)
    domain = parsed.netloc.replace('www.', '')
    slug = normalize_name(''.join(domain.split('.')))
    return slug

def get_domain_root(url):
    try:
        parsed = urlparse(url)
        host = parsed.netloc.replace('www.', '')
        parts = host.split('.')
        if len(parts) >= 2:
            return f"{parts[-2]}.{parts[-1]}"
        return host
    except Exception:
        return ""

TECHCRUNCH_URL = 'https://techcrunch.com/category/startups/'
HEADERS = config.HEADERS

def get_article_links(min_date=None, max_pages=10):
    """
    Crawl TechCrunch articles from multiple categories, get all articles in the date range [min_date, today]
    """
    today = date.today()
    if min_date is None:
        min_date = today - timedelta(days=30)  # Mặc định 30 ngày
    links = []
    
    # Crawl từ nhiều category để có nhiều bài viết hơn
    categories = [
        'https://techcrunch.com/category/startups/'
    ]
    
    for category_url in categories:
        logger.info(f"Crawling category: {category_url}")
        
        for page in range(1, max_pages + 1):
            page_url = f"{category_url}page/{page}/" if page > 1 else category_url
            try:
                logger.info(f"Đang tìm nạp trang {page}: {page_url}")
                resp = requests.get(page_url, headers=HEADERS, timeout=10)
                logger.info(f"Trạng thái trang {page}: {resp.status_code}")
                soup = BeautifulSoup(resp.text, 'html.parser')
                all_older = True
                
                # Tìm tất cả bài viết trên trang
                cards = soup.find_all('article', class_='wp-block-tc2023-post-card')
                logger.info(f"Trang {page}: Tìm thấy {len(cards)} bài viết với 'wp-block-tc2023-post-card'")
                
                if not cards:
                    cards = soup.find_all('div', class_='wp-block-techcrunch-card')
                    logger.info(f"Trang {page}: Tìm thấy {len(cards)} thẻ với 'wp-block-techcrunch-card' (dự phòng)")
                
                if not cards:
                    cards = soup.find_all('article')
                    logger.info(f"Trang {page}: Tìm thấy {len(cards)} bài viết (dự phòng)")
                
                if not cards:
                    cards = soup.find_all('div', class_=lambda x: x and 'card' in x)
                    logger.info(f"Trang {page}: Tìm thấy {len(cards)} div với 'card' trong class (dự phòng)")
                
                for card in cards:
                    title_h2 = card.find('h2', class_='wp-block-tc2023-post-card__title')
                    a_tag = title_h2.find('a') if title_h2 else None
                    
                    if not a_tag:
                        content = card.find('div', class_='wp-block-techcrunch-card__content')
                        if not content:
                            content = card.find('div', class_=lambda x: x and 'content' in x)
                        if not content:
                            content = card
                        
                        if content:
                            a_tag = content.find('a')
                    
                    if a_tag:
                        url = a_tag['href']
                        
                        # Chỉ lấy bài viết thực sự, không phải category pages
                        if '/category/' in url or '/tag/' in url:
                            continue
                            
                        logger.info(f"Tìm thấy URL: {url}")
                        
                        time_tag = card.find('time')
                        
                        pub_date = None
                        if time_tag and time_tag.has_attr('datetime'):
                            try:
                                pub_date = datetime.fromisoformat(time_tag['datetime'].replace('Z', '+00:00')).date()
                                logger.info(f"Tìm thấy ngày: {pub_date} từ datetime: {time_tag['datetime']}")
                            except Exception as e:
                                logger.warning(f"Lỗi khi phân tích ngày tháng: {e}. Sử dụng ngày hiện tại làm dự phòng.")
                                pub_date = today
                        else:
                            logger.info("Không tìm thấy thẻ thời gian, sử dụng ngày hiện tại làm dự phòng.")
                            pub_date = today
                        
                        if pub_date is None:
                            logger.warning(f"Không thể xác định ngày xuất bản cho bài viết: {url}. Bỏ qua.")
                            continue

                        logger.info(f"Kiểm tra phạm vi ngày: {min_date} <= {pub_date} <= {today}")
                        if min_date <= pub_date <= today:
                            links.append((url, pub_date.isoformat()))
                            all_older = False
                            logger.info(f"Đã thêm bài viết: {url} | {pub_date}")
                        else:
                            logger.info(f"Đã bỏ qua bài viết (ngoài phạm vi ngày): {url} | {pub_date}")
                    else:
                        logger.warning("Không tìm thấy liên kết bài viết chính (a_tag) trong thẻ.")
                
                if all_older:
                    logger.info(f"Trang {page}: Tất cả bài viết đều cũ hơn {min_date}, dừng lại.")
                    break
                        
            except Exception as e:
                logger.error(f"[LỖI][TechCrunch] Trang {page}: {e}")
                break
    
    logger.info(f"Tổng số bài viết tìm thấy: {len(links)}")
    return links

def extract_article_links_and_context(soup, company_name):
    """
    Extract all anchor tags (<a>) in the article, along with surrounding context
    """
    results = []
    company_norm = normalize_company_name(company_name)
    for a in soup.find_all('a', href=True):
        url = a['href']
        anchor_text = a.get_text(strip=True)
        parent = a.parent
        context = ''
        if parent:
            text = parent.get_text(separator=' ', strip=True)
            idx = text.find(anchor_text)
            if idx != -1:
                before = text[:idx].strip().split('.')[-1]
                after = text[idx+len(anchor_text):].strip().split('.')[0]
                context = f"{before} [{anchor_text}] {after}".strip()
            else:
                context = text
        domain = urlparse(url).netloc.lower()
        results.append({
            'url': url,
            'anchor_text': anchor_text,
            'context': context,
            'domain': domain,
            'company_norm': company_norm
        })
    return results

def extract_best_links_from_anchors(links_context, company_name, top_n=3):
    """
    Return top N website and top N linkedin with highest scores
    """
    if fuzz is None:
        logger.warning("Thư viện 'thefuzz' không được cài đặt. Bỏ qua trích xuất liên kết dựa trên độ mờ.")
        return [], []

    norm_company = normalize_name(company_name)
    website_candidates = []
    linkedin_candidates = []
    
    for link in links_context:
        url = link['url']
        domain = urlparse(url).netloc.lower()
        domain_slug = extract_domain_slug(url)
        score = fuzz.partial_ratio(norm_company, domain_slug)
        
        # Website: exclude linkedin, facebook, crunchbase...
        if not any(x in domain for x in ['linkedin.com', 'facebook.com', 'twitter.com', 'crunchbase.com', 'news.', '/news/']):
            website_candidates.append((url, score))
        
        # LinkedIn
        if 'linkedin.com/company' in url:
            linkedin_candidates.append((url, score))
    
    # Sort and get top N
    website_candidates = sorted(website_candidates, key=lambda x: x[1], reverse=True)[:top_n]
    linkedin_candidates = sorted(linkedin_candidates, key=lambda x: x[1], reverse=True)[:top_n]
    
    websites = [w for w, s in website_candidates]
    linkedins = [l for l, s in linkedin_candidates]
    
    return websites, linkedins

def crawl_techcrunch():
    """
    Crawl TechCrunch articles and extract company information
    """
    today = date.today()
    min_date = today - timedelta(days=30)  # Tăng từ 7 lên 30 ngày
    article_links = get_article_links(min_date=min_date, max_pages=10)  # Tăng max_pages
    logger.info(f'Tìm thấy {len(article_links)} bài viết TechCrunch.')
    
    # Sử dụng DB thay vì CSV cho deduplication
    existing_entries = load_existing_entries()
    unique_entries = {}
    
    logger.info(f"Đang xử lý {len(article_links)} bài viết...")
    
    for i, (url, pub_date) in enumerate(article_links):
        logger.info(f"\n=== Đang xử lý Bài viết {i+1}/{len(article_links)} ===")
        logger.info(f"URL: {url}")
        logger.info(f"Ngày: {pub_date}")
        
        source = "TechCrunch"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            title_tag = soup.find('h1')
            title = title_tag.get_text(strip=True) if title_tag else ''
            logger.info(f"Tiêu đề: {title}")
            
            article_body = soup.find('div', class_='entry-content')
            article_text = ""
            if article_body:
                paragraphs = article_body.find_all('p')
                article_text = " ".join(p.get_text() for p in paragraphs)
                logger.info(f"Độ dài nội dung: {len(article_text)} ký tự")
            else:
                logger.warning(f"[BỎ QUA][KHÔNG CÓ NỘI DUNG] {url}")
                continue
            
            logger.info("Đang kiểm tra xem có phải bài viết về gọi vốn không...")
            if not is_funding_article_llm(article_text):
                logger.info(f"[BỎ QUA][KHÔNG PHẢI GỌI VỐN] Tiêu đề: {title} | Ngày: {pub_date} | URL: {url}")
                continue
            
            logger.info("✅ Bài viết liên quan đến gọi vốn")
            
            # Trích xuất thông tin công ty và ngày gọi vốn sớm
            logger.info("Đang trích xuất thông tin công ty và ngày gọi vốn...")
            temp_info = extract_company_name_and_raised_date_llm(article_text, min_date.isoformat(), today.isoformat())
            
            # Xử lý trường hợp LLM trả về một list hoặc một dict
            if isinstance(temp_info, list):
                infos = temp_info
            else:
                infos = [temp_info] # Đảm bảo luôn là list để lặp

            logger.info(f"Tìm thấy {len(infos)} thông tin công ty")
            
            for j, company_info in enumerate(infos):
                logger.info(f"Đang xử lý thông tin công ty {j+1}/{len(infos)}")
                
                company_name = (company_info.get('company_name') or '').strip()
                raised_date = (company_info.get('raised_date') or '').strip() or pub_date
                amount_raised = (company_info.get('amount') or '').strip()
                funding_round = (company_info.get('round_type') or '').strip()
                
                if not company_name:
                    logger.warning(f"[BỎ QUA][KHÔNG CÓ TÊN CÔNG TY] Bài viết: {url}")
                    continue

                logger.info(f"Công ty: {company_name}")
                logger.info(f"Ngày gọi vốn: {raised_date}")
                logger.info(f"Số tiền: {amount_raised}")
                logger.info(f"Vòng gọi vốn: {funding_round}")
                
                key = (
                    normalize_company_name(company_name),
                    normalize_date(raised_date),
                    url
                )
                if key in existing_entries:
                    logger.info(f"[BỎ QUA][TRÙNG LẶP ĐÃ CÓ] {company_name} | {raised_date} | {url}")
                    continue
                if key in unique_entries:
                    logger.info(f"[BỎ QUA][TRÙNG LẶP MỚI] {company_name} | {raised_date} | {url}")
                    continue
                
                # Tích hợp logic trích xuất liên kết từ anchor và LLM
                website = ''
                linkedin = ''
                llm_guesses = None
                llm_linkedin_guess = None

                # 1. Trích xuất liên kết từ anchor trong bài viết
                logger.info("Đang trích xuất liên kết từ anchor trong bài viết...")
                links_context = extract_article_links_and_context(soup, company_name)
                websites_from_anchors, linkedins_from_anchors = extract_best_links_from_anchors(links_context, company_name, top_n=3)
                website = websites_from_anchors[0] if websites_from_anchors else ''
                linkedin = linkedins_from_anchors[0] if linkedins_from_anchors else ''
                
                logger.info(f"Website từ anchor: {website if website else 'Không tìm thấy'}")
                logger.info(f"LinkedIn từ anchor: {linkedin if linkedin else 'Không tìm thấy'}")

                # 2. Nếu chưa có, sử dụng LLM để trích xuất từ nội dung bài viết
                if not website or not linkedin:
                    logger.info("Đang sử dụng LLM để trích xuất liên kết từ nội dung bài viết...")
                    result_from_llm_links = extract_company_info_llm(article_text, links_context)
                    if result_from_llm_links:
                        # Cải thiện logic xử lý kết quả từ LLM
                        if not website:
                            website = result_from_llm_links.get('website', '').strip()
                            if not website and result_from_llm_links.get('website_guesses'):
                                website_guesses = result_from_llm_links.get('website_guesses', [])
                                if isinstance(website_guesses, list) and len(website_guesses) > 0:
                                    website = website_guesses[0].strip()
                        if not linkedin:
                            linkedin = result_from_llm_links.get('linkedin', '').strip()
                            if not linkedin and result_from_llm_links.get('linkedin_guess'):
                                linkedin = result_from_llm_links.get('linkedin_guess', '').strip()
                        
                        logger.info(f"[LLM][LÝ DO] {company_name} | độ tin cậy: {result_from_llm_links.get('confidence', '')} | lý do: {result_from_llm_links.get('reasoning', '')}")
                        logger.info(f"Website từ LLM: {website if website else 'Không tìm thấy'}")
                        logger.info(f"LinkedIn từ LLM: {linkedin if linkedin else 'Không tìm thấy'}")

                # 3. Nếu vẫn chưa có, sử dụng Tavily search với logic mới
                if not website and company_name:
                    logger.info("Fallback: Đang tìm kiếm website bằng Tavily...")
                    website = find_company_website(company_name)
                
                if not linkedin and company_name:
                    logger.info("Fallback: Đang tìm kiếm LinkedIn bằng Tavily...")
                    linkedin = find_company_linkedin(company_name)
                
                crawl_date = today.isoformat()
                
                logger.info(f"Website cuối cùng: {website}")
                logger.info(f"LinkedIn cuối cùng: {linkedin}")
                
                entry = {
                    'raised_date': raised_date,
                    'company_name': company_name,
                    'website': website,
                    'linkedin': linkedin,
                    'article_url': url,
                    'source': source,
                    'crawl_date': crawl_date,
                    'amount_raised': amount_raised,
                    'funding_round': funding_round
                }
                unique_entries[key] = entry
                logger.info(f"✅ [THÊM] {company_name} | {raised_date} | {url}")
                logger.info(f"   Số tiền: {amount_raised}")
                logger.info(f"   Vòng gọi vốn: {funding_round}")
                logger.info(f"   Website: {website}")
                logger.info(f"   LinkedIn: {linkedin}")
                
        except Exception as e:
            logger.error(f"[LỖI] Xử lý bài viết {url}: {e}")
    
    logger.info(f"\n=== TÓM TẮT ===")
    logger.info(f"Tổng số bài viết đã xử lý: {len(article_links)}")
    logger.info(f"Tổng số bản ghi duy nhất tìm thấy: {len(unique_entries)}")
    
    for key, entry in unique_entries.items():
        logger.info(f"Bản ghi: {entry['company_name']} | {entry['raised_date']} | {entry['website']}")
    
    return list(unique_entries.values())

if __name__ == '__main__':
    logger.info("=== TechCrunch Crawler ===")
    entries = crawl_techcrunch()
    if entries:
        logger.info(f'Tìm thấy {len(entries)} bản ghi TechCrunch.')
    else:
        logger.info('Không tìm thấy bản ghi TechCrunch nào.')
    logger.info("Hoàn tất. Kiểm tra cơ sở dữ liệu để xem kết quả.") 