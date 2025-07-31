#!/usr/bin/env python3
"""
List Page Crawler - Crawl trang danh sách tin tức và tự động tìm bài báo funding
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
from typing import List, Dict, Any
from utils.logger import logger
from llm_utils import extract_structured_data_llm

class ListPageCrawler:
    def __init__(self):
        self.funding_keywords = [
            'funding', 'raises', 'raised', 'investment', 'series', 'seed',
            'venture', 'capital', 'backed', 'invested', 'closes', 'secures',
            'receives', 'announces', 'fundraising', 'round'
        ]
    
    async def extract_article_links(self, list_page_url: str, max_articles: int = 200, start_date: str = None, end_date: str = None) -> List[Dict[str, str]]:
        """
        Trích xuất danh sách link bài báo từ trang danh sách với lọc theo khoảng thời gian
        
        Args:
            list_page_url: URL trang danh sách (ví dụ: https://techcrunch.com/startups/)
            max_articles: Số lượng bài báo tối đa để crawl
            start_date: Ngày bắt đầu (YYYY-MM-DD format)
            end_date: Ngày kết thúc (YYYY-MM-DD format)
            
        Returns:
            List các dict chứa {url, title, preview, pub_date}
        """
        try:
            logger.info(f"Extracting article links from: {list_page_url}")
            if start_date and end_date:
                logger.info(f"Date range filter: {start_date} to {end_date}")
            
            # Tạo SSL context để bỏ qua certificate verification
            import ssl
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(list_page_url, headers=headers, timeout=30) as response:
                    if response.status != 200:
                        logger.error(f"Failed to fetch {list_page_url}: {response.status}")
                        return []
                    
                    html = await response.text()
            
            # Debug: Log một phần HTML để kiểm tra
            logger.info(f"HTML content length: {len(html)}")
            logger.info(f"HTML preview: {html[:500]}...")
            
            soup = BeautifulSoup(html, 'html.parser')
            articles = []
            
            # Kết hợp tất cả các strategy lấy link
            article_links = []
            # Strategy 1: Tìm link trong các thẻ article, h1, h2, h3
            for tag in soup.find_all(['article', 'h1', 'h2', 'h3']):
                links = tag.find_all('a', href=True)
                article_links.extend(links)
            # Strategy 2: Tìm link có pattern URL bài báo (bao gồm Crunchbase)
            links2 = soup.find_all('a', href=True)
            article_links.extend([link for link in links2 if self._looks_like_article_url(link['href'])])
            # Strategy 3: Tìm link có class/title chứa từ khóa bài báo
            article_links.extend([link for link in links2 if self._has_article_indicators(link)])
            # Strategy 4: Đặc biệt cho Crunchbase - tìm link có href chứa /2025/ hoặc /2024/
            article_links.extend([link for link in links2 if '/2025/' in link.get('href', '') or '/2024/' in link.get('href', '')])
            # Loại trùng lặp
            seen = set()
            unique_links = []
            for link in article_links:
                href = link.get('href', '')
                if href and href not in seen:
                    unique_links.append(link)
                    seen.add(href)
            article_links = unique_links
            logger.info(f"Total unique article links found: {len(article_links)}")
            
            # Lọc và chuẩn hóa URLs
            logger.info(f"Processing {len(article_links)} links from strategies...")
            
            processed_count = 0
            for link in article_links:
                if processed_count >= max_articles:
                    break
                    
                href = link.get('href', '')
                title = link.get_text(strip=True)
                
                # Bỏ qua link rỗng hoặc không có title
                if not href or not title:
                    continue
                
                # Chuẩn hóa URL
                full_url = urljoin(list_page_url, href)
                
                # Kiểm tra xem có phải URL bài báo không
                if not self._looks_like_article_url(full_url):
                    logger.info(f"Processing link {processed_count + 1}: {title[:50]} -> {full_url}")
                    logger.info(f"  - looks_like_article_url: False")
                    continue
                
                # Kiểm tra xem có phải list page URL không
                if self._is_list_page_url(full_url):
                    logger.info(f"Processing link {processed_count + 1}: {title[:50]} -> {full_url}")
                    logger.info(f"  - is_list_page_url: True")
                    continue
                
                # Trích xuất ngày xuất bản từ URL hoặc metadata
                pub_date = self._extract_publication_date(full_url, link, soup)
                
                # Lọc theo khoảng thời gian nếu có
                if start_date and end_date and pub_date:
                    if not self._is_date_in_range(pub_date, start_date, end_date):
                        logger.info(f"Skipping article outside date range: {title[:50]} (pub_date: {pub_date})")
                        continue
                
                # Trích xuất preview text
                preview = self._extract_preview_text(link)
                
                articles.append({
                    'url': full_url,
                    'title': title,
                    'preview': preview,
                    'pub_date': pub_date
                })
                
                processed_count += 1
                logger.info(f"✅ Added article: {title[:50]} -> {full_url}")
            
            logger.info(f"Found {len(articles)} potential articles from {list_page_url}")
            if articles:
                logger.info("Sample URLs found:")
                for i, article in enumerate(articles[:5]):
                    logger.info(f"   {i+1}. {article['title'][:80]} -> {article['url']}")
            
            return articles
            
        except Exception as e:
            logger.error(f"Error extracting article links from {list_page_url}: {e}")
            return []
    
    def _looks_like_article_url(self, url: str) -> bool:
        """Kiểm tra URL có giống bài báo không"""
        # Loại bỏ các URL không phải bài báo
        exclude_patterns = [
            r'/tag/', r'/category/', r'/author/', r'/page/', r'/search',
            r'/about', r'/contact', r'/privacy', r'/terms', r'/login',
            r'\.(jpg|jpeg|png|gif|pdf|doc|zip)$', r'#', r'\?page='
        ]
        
        for pattern in exclude_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return False
        
        # Đặc biệt xử lý cho Crunchbase
        if 'crunchbase.com' in url:
            # Crunchbase article URLs thường có format: /2025/07/28/article-title/
            if re.search(r'/\d{4}/\d{2}/\d{2}/', url):
                return True
            # Hoặc có /section/ + article path
            if '/section/' in url and len(urlparse(url).path.strip('/').split('/')) > 2:
                return True
        
        # URL phải có path dài hơn 1 ký tự
        parsed = urlparse(url)
        return len(parsed.path.strip('/')) > 1
    
    def _is_list_page_url(self, url: str) -> bool:
        """Kiểm tra URL có phải trang danh sách không"""
        parsed = urlparse(url)
        path = parsed.path.strip('/')
        
        # Đặc biệt xử lý cho TechCrunch - URLs có format /2025/07/29/article-title/
        if 'techcrunch.com' in url:
            # Nếu có pattern date (YYYY/MM/DD) thì là bài báo, không phải list page
            if re.search(r'^\d{4}/\d{2}/\d{2}/', path):
                return False
        
        # Đặc biệt xử lý cho Crunchbase sections
        if '/section/' in url:
            path_parts = path.split('/')
            # Nếu có nhiều hơn 2 phần trong path (section + article), thì là bài báo
            if len(path_parts) > 2:
                return False
        
        # Các pattern cho list pages
        list_patterns = [
            r'^$',  # Root path only
            r'/page/', r'/category/', r'/tag/',
            r'^startups$', r'^news$', r'^articles$'  # Exact matches
        ]
        
        for pattern in list_patterns:
            if re.search(pattern, path, re.IGNORECASE):
                return True
        return False
    
    def _has_article_indicators(self, link) -> bool:
        """Kiểm tra link có dấu hiệu là bài báo không"""
        # Kiểm tra class, id, title có chứa từ khóa bài báo
        article_indicators = ['article', 'post', 'story', 'news', 'title', 'headline']
        
        for attr in ['class', 'id', 'title', 'alt']:
            value = link.get(attr, '')
            if isinstance(value, list):
                value = ' '.join(value)
            
            for indicator in article_indicators:
                if indicator.lower() in value.lower():
                    return True
        
        return False
    
    def _extract_preview_text(self, link) -> str:
        """Trích xuất preview text từ link"""
        # Tìm text trong các thẻ lân cận
        parent = link.parent
        if parent:
            # Tìm thẻ p, div, span gần nhất
            for tag in parent.find_all(['p', 'div', 'span'], limit=3):
                text = tag.get_text(strip=True)
                if len(text) > 20 and len(text) < 200:
                    return text
        
        return ""
    
    def _extract_publication_date(self, url: str, link_element, soup) -> str:
        """
        Trích xuất ngày xuất bản từ URL, thẻ time, meta, span chứa ngày
        """
        try:
            # 1. Từ URL pattern (TechCrunch: /2025/07/29/)
            url_date_match = re.search(r'/([0-9]{4})/([0-9]{2})/([0-9]{2})/', url)
            if url_date_match:
                year, month, day = url_date_match.groups()
                return f"{year}-{month}-{day}"
            # 2. Từ thẻ <time datetime="...">
            time_tag = link_element.find('time')
            if time_tag and time_tag.has_attr('datetime'):
                date_match = re.search(r'([0-9]{4}-[0-9]{2}-[0-9]{2})', time_tag['datetime'])
                if date_match:
                    return date_match.group(1)
            # 3. Từ meta property hoặc name chứa date
            for meta in soup.find_all('meta'):
                for attr in ['property', 'name']:
                    if meta.has_attr(attr) and 'date' in meta[attr].lower() and meta.has_attr('content'):
                        date_match = re.search(r'([0-9]{4}-[0-9]{2}-[0-9]{2})', meta['content'])
                        if date_match:
                            return date_match.group(1)
            # 4. Từ các span/div chứa ngày
            for tag in soup.find_all(['span', 'div']):
                text = tag.get_text(strip=True)
                date_match = re.search(r'([0-9]{4}-[0-9]{2}-[0-9]{2})', text)
                if date_match:
                    return date_match.group(1)
            return None
        except Exception as e:
            logger.warning(f"Error extracting publication date: {e}")
            return None
    
    def _is_date_in_range(self, pub_date: str, start_date: str, end_date: str) -> bool:
        """
        Kiểm tra xem ngày xuất bản có trong khoảng thời gian không
        
        Args:
            pub_date: Ngày xuất bản (YYYY-MM-DD)
            start_date: Ngày bắt đầu (YYYY-MM-DD)
            end_date: Ngày kết thúc (YYYY-MM-DD)
            
        Returns:
            True nếu ngày trong khoảng
        """
        try:
            from datetime import datetime
            
            if not pub_date:
                return True  # Nếu không có ngày, cho phép qua
            
            pub_dt = datetime.strptime(pub_date, '%Y-%m-%d')
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            
            return start_dt <= pub_dt <= end_dt
            
        except Exception as e:
            logger.warning(f"Error checking date range: {e}")
            return True  # Nếu có lỗi, cho phép qua
    
    async def filter_funding_articles(self, articles: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Lọc ra các bài báo funding chuẩn như techcrunch_crawler/finsmes_crawler:
        - Fetch nội dung thật của bài báo
        - Nếu không lấy được nội dung hoặc quá ngắn, bỏ qua và log lý do
        - Dùng is_funding_article_llm(article_text) để xác định bài funding
        - Nếu không phải, log lý do và bỏ qua
        - Nếu là bài funding thì giữ lại
        """
        from llm_utils import is_funding_article_llm
        import requests
        funding_articles = []
        for article in articles:
            url = article.get('url')
            title = article.get('title', '')
            try:
                resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code != 200:
                    logger.info(f"[SKIP][NO CONTENT] {url} | status_code={resp.status_code}")
                    continue
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, 'html.parser')
                # Lấy nội dung chính (ưu tiên các div phổ biến)
                content_div = None
                for selector in [
                    'div.wp-block-post-content', 'div.entry-content', 'div.post-content',
                    'div.article-content', 'div.article-body', 'article .content', 'div.content', 'article']:
                    content_div = soup.select_one(selector)
                    if content_div:
                        break
                article_text = ''
                if content_div:
                    paragraphs = content_div.find_all('p')
                    article_text = " ".join(p.get_text() for p in paragraphs)
                if not article_text or len(article_text.strip()) < 200:
                    logger.info(f"[SKIP][NO CONTENT] {url} | Title: {title}")
                    continue
                # Dùng LLM chuẩn để xác định funding
                if not is_funding_article_llm(article_text):
                    logger.info(f"[SKIP][NOT FUNDING] Title: {title} | URL: {url}")
                    continue
                # Nếu là funding, giữ lại
                funding_articles.append(article)
                logger.info(f"✅ Article is funding-related: {title}")
            except Exception as e:
                logger.info(f"[SKIP][ERROR] {url} | {e}")
                continue
        logger.info(f"Filtered {len(funding_articles)} funding articles from {len(articles)} total articles (by full content check)")
        return funding_articles
    
    async def crawl_list_page(self, list_page_url: str, max_articles: int = 200, start_date: str = None, end_date: str = None) -> List[Dict[str, str]]:
        """
        Crawl trang danh sách và lọc bài báo funding
        
        Args:
            list_page_url: URL trang danh sách
            max_articles: Số lượng bài báo tối đa
            start_date: Ngày bắt đầu (YYYY-MM-DD)
            end_date: Ngày kết thúc (YYYY-MM-DD)
            
        Returns:
            List các bài báo funding
        """
        try:
            # Bước 1: Trích xuất tất cả link bài báo
            articles = await self.extract_article_links(list_page_url, max_articles, start_date, end_date)
            
            if not articles:
                logger.warning(f"No articles found on {list_page_url}")
                return []
            
            # Bước 2: Lọc bài báo funding
            funding_articles = await self.filter_funding_articles(articles)
            
            logger.info(f"Filtered {len(funding_articles)} funding articles from {len(articles)} total articles")
            
            return funding_articles
            
        except Exception as e:
            logger.error(f"Error crawling list page {list_page_url}: {e}")
            return []

# Wrapper functions
async def crawl_list_page_async(list_page_url: str, max_articles: int = 200, start_date: str = None, end_date: str = None) -> List[Dict[str, str]]:
    """Async wrapper for list page crawling with date range support"""
    crawler = ListPageCrawler()
    return await crawler.crawl_list_page(list_page_url, max_articles, start_date, end_date)

def crawl_list_page(list_page_url: str, max_articles: int = 200, start_date: str = None, end_date: str = None) -> List[Dict[str, str]]:
    """Sync wrapper for list page crawling with date range support"""
    import nest_asyncio
    try:
        nest_asyncio.apply()
        return asyncio.run(crawl_list_page_async(list_page_url, max_articles, start_date, end_date))
    except ImportError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(crawl_list_page_async(list_page_url, max_articles, start_date, end_date))
        loop.close()
        return result 