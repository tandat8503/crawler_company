#!/usr/bin/env python3
"""
AI Auto-Discovery Module
Tự động phát hiện và crawl bất kỳ trang web nào mà không cần cấu hình trước
"""

import asyncio
import aiohttp
import ssl
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
from typing import List, Dict, Any, Optional
from utils.logger import logger
from llm_utils import llm_prompt, safe_parse_json
import config

class AIAutoDiscovery:
    def __init__(self):
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    
    async def analyze_website_structure(self, url: str) -> Dict[str, Any]:
        """
        Phân tích cấu trúc website bằng AI để hiểu cách crawl
        """
        try:
            # Validate URL first
            if not self._is_valid_url(url):
                return {"error": f"Invalid URL format: {url}", "success": False}
            
            # Normalize URL
            url = self._normalize_url(url)
            
            logger.info(f"🔍 Analyzing website structure: {url}")
            
            # Fetch website content
            async with aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=self.ssl_context),
                headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as session:
                async with session.get(url, allow_redirects=True) as response:
                    if response.status != 200:
                        error_msg = f"HTTP {response.status}: {response.reason}"
                        if response.status == 403:
                            error_msg += " - Website có thể đang chặn bot. Thử lại sau hoặc sử dụng VPN."
                        elif response.status == 429:
                            error_msg += " - Quá nhiều request. Vui lòng thử lại sau vài phút."
                        elif response.status == 503:
                            error_msg += " - Website tạm thời không khả dụng."
                        return {"error": error_msg, "success": False}
                    
                    html = await response.text()
                    
                    # Check if we got valid HTML
                    if len(html) < 1000:
                        return {"error": "Website returned too little content", "success": False}
                    
                    # Check for bot detection
                    bot_detection_indicators = [
                        "access denied", "blocked", "forbidden", "bot detected",
                        "captcha", "cloudflare", "security check", "rate limit",
                        "temporarily blocked", "suspicious activity"
                    ]
                    
                    html_lower = html.lower()
                    for indicator in bot_detection_indicators:
                        if indicator in html_lower:
                            return {
                                "error": f"Website đang chặn bot (detected: {indicator}). Thử lại sau hoặc sử dụng VPN.",
                                "success": False,
                                "bot_blocked": True
                            }
            
            # Extract key information
            soup = BeautifulSoup(html, 'html.parser')
            
            # Get basic info
            title = soup.find('title')
            title_text = title.get_text(strip=True) if title else ""
            
            # Find navigation links
            nav_links = self._extract_navigation_links(soup, url)
            
            # Find potential article links
            article_links = self._extract_potential_article_links(soup, url)
            
            # Analyze with AI
            analysis = await self._ai_analyze_website(
                url, title_text, nav_links, article_links, html[:2000]
            )
            
            logger.info(f"✅ Website analysis completed: {analysis['website_type']} (confidence: {analysis['confidence']})")
            
            return {
                "url": url,
                "title": title_text,
                "nav_links": nav_links[:10],  # Limit to 10
                "article_links": article_links[:10],  # Limit to 10
                "analysis": analysis,
                "success": True
            }
            
        except asyncio.TimeoutError:
            logger.error(f"Timeout analyzing website {url}")
            return {"error": "Request timeout - website may be slow or unavailable", "success": False}
        except aiohttp.ClientError as e:
            logger.error(f"Network error analyzing website {url}: {e}")
            if "403" in str(e):
                return {"error": "Website đang chặn bot (403 Forbidden). Thử lại sau hoặc sử dụng VPN.", "success": False, "bot_blocked": True}
            elif "429" in str(e):
                return {"error": "Quá nhiều request (429). Vui lòng thử lại sau vài phút.", "success": False}
            else:
                return {"error": f"Network error: {str(e)}", "success": False}
        except Exception as e:
            logger.error(f"Error analyzing website {url}: {e}")
            return {"error": str(e), "success": False}
    
    def _is_valid_url(self, url: str) -> bool:
        """Validate if input is a valid URL"""
        import re
        from urllib.parse import urlparse
        
        # Normalize URL first
        normalized_url = self._normalize_url(url)
        
        # Check if it's a valid URL format
        try:
            result = urlparse(normalized_url)
            if not all([result.scheme, result.netloc]):
                return False
            
            # Additional regex check for common patterns
            url_pattern = re.compile(
                r'^https?://'  # http:// or https://
                r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
                r'localhost|'  # localhost...
                r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
                r'(?::\d+)?'  # optional port
                r'(?:/?|[/?]\S+)$', re.IGNORECASE)
            
            return bool(url_pattern.match(normalized_url))
        except:
            return False
    
    def _normalize_url(self, url: str) -> str:
        """Normalize URL to ensure proper format"""
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # Remove trailing slash for consistency
        if url.endswith('/'):
            url = url[:-1]
        
        return url
    
    def _extract_navigation_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """Extract navigation links from website"""
        nav_links = []
        
        # Common navigation selectors
        nav_selectors = [
            'nav a', 'header a', '.navigation a', '.nav a', '.menu a',
            '.navbar a', '.main-nav a', '.site-nav a', '.primary-nav a'
        ]
        
        for selector in nav_selectors:
            links = soup.select(selector)
            for link in links:
                href = link.get('href')
                if href:
                    full_url = urljoin(base_url, href)
                    if self._is_valid_nav_link(full_url, base_url):
                        nav_links.append(full_url)
        
        return list(set(nav_links))  # Remove duplicates
    
    def _extract_potential_article_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """Extract potential article links"""
        article_links = []
        
        # Common article selectors
        article_selectors = [
            'article a', '.post a', '.article a', '.news a', '.story a',
            '.content a', '.main-content a', '.entry a', '.blog a'
        ]
        
        for selector in article_selectors:
            links = soup.select(selector)
            for link in links:
                href = link.get('href')
                if href:
                    full_url = urljoin(base_url, href)
                    if self._looks_like_article_url(full_url):
                        article_links.append(full_url)
        
        return list(set(article_links))
    
    def _is_valid_nav_link(self, url: str, base_url: str) -> bool:
        """Check if URL is a valid navigation link"""
        try:
            parsed = urlparse(url)
            base_parsed = urlparse(base_url)
            
            # Must be same domain
            if parsed.netloc and parsed.netloc != base_parsed.netloc:
                return False
            
            # Must have path
            if not parsed.path or parsed.path == '/':
                return False
            
            # Exclude common non-article paths
            exclude_patterns = [
                r'/tag/', r'/category/', r'/author/', r'/page/', r'/search',
                r'/about', r'/contact', r'/privacy', r'/terms', r'/login',
                r'\.(jpg|jpeg|png|gif|pdf|doc|zip)$', r'#', r'\?page='
            ]
            
            for pattern in exclude_patterns:
                if re.search(pattern, url, re.IGNORECASE):
                    return False
            
            return True
        except:
            return False
    
    def _looks_like_article_url(self, url: str) -> bool:
        """Check if URL looks like an article"""
        try:
            parsed = urlparse(url)
            path = parsed.path.strip('/')
            
            # Must have meaningful path
            if len(path) < 10:
                return False
            
            # Check for date patterns
            if re.search(r'/\d{4}/\d{2}/\d{2}/', url):
                return True
            
            # Check for article-like patterns
            article_patterns = [
                r'/article/', r'/post/', r'/news/', r'/story/',
                r'/blog/', r'/content/', r'/entry/', r'/feature/'
            ]
            
            for pattern in article_patterns:
                if re.search(pattern, url, re.IGNORECASE):
                    return True
            
            # Check for long slug (likely article)
            path_parts = path.split('/')
            if len(path_parts) >= 2:
                last_part = path_parts[-1]
                if len(last_part) > 20:  # Long slug
                    return True
            
            return False
        except:
            return False
    
    async def _ai_analyze_website(self, url: str, title: str, nav_links: List[str], 
                                article_links: List[str], html_sample: str) -> Dict[str, Any]:
        """Use AI to analyze website structure and determine crawling strategy"""
        
        prompt = f"""
        You are an expert web crawler analyst. Analyze this website and determine the best crawling strategy.
        
        Website URL: {url}
        Title: {title}
        Navigation Links: {nav_links[:5]}
        Sample Article Links: {article_links[:5]}
        HTML Sample: {html_sample[:1000]}
        
        Analyze and provide:
        1. Website type (news, blog, e-commerce, etc.)
        2. Best crawling strategy
        3. Article link patterns
        4. Date extraction method
        5. Content extraction selectors
        
        Return JSON format:
        {{
            "website_type": "string",
            "crawling_strategy": "string",
            "article_patterns": ["pattern1", "pattern2"],
            "date_extraction": "method",
            "content_selectors": ["selector1", "selector2"],
            "confidence": "high|medium|low",
            "recommendations": ["rec1", "rec2"]
        }}
        """
        
        try:
            response = await asyncio.to_thread(llm_prompt, prompt, max_tokens=1024, temperature=0.1)
            if response:
                analysis = safe_parse_json(response)
                if analysis:
                    return analysis
        except Exception as e:
            logger.warning(f"AI analysis failed: {e}")
        
        # Fallback analysis
        return {
            "website_type": "unknown",
            "crawling_strategy": "generic",
            "article_patterns": [],
            "date_extraction": "url_or_meta",
            "content_selectors": ["article", ".content", ".post-content"],
            "confidence": "low",
            "recommendations": ["Use generic crawling strategy"]
        }
    
    async def auto_crawl_website(self, url: str, max_articles: int = 20) -> List[Dict[str, Any]]:
        """
        Tự động crawl website mà không cần cấu hình trước
        """
        try:
            logger.info(f"🤖 Starting AI Auto-Discovery for: {url}")
            
            # Step 1: Analyze website structure
            analysis = await self.analyze_website_structure(url)
            if not analysis.get('success'):
                return [{"error": analysis.get('error', 'Analysis failed'), "success": False}]
            
            logger.info(f"✅ Website analysis completed: {analysis['analysis']['website_type']}")
            
            # Step 2: Find article pages
            article_urls = await self._discover_article_urls(url, analysis, max_articles)
            
            if not article_urls:
                return [{"error": "No article URLs found - website may not have clear article structure", "success": False}]
            
            logger.info(f"📰 Found {len(article_urls)} potential article URLs")
            
            # Step 3: Crawl articles with retry logic
            results = []
            successful_count = 0
            
            for i, article_url in enumerate(article_urls[:max_articles]):
                try:
                    logger.info(f"📄 Crawling article {i+1}/{min(len(article_urls), max_articles)}: {article_url}")
                    
                    result = await self._crawl_single_article_with_retry(article_url, analysis)
                    if result and result.get('success'):
                        results.append(result)
                        successful_count += 1
                        
                        # Log progress
                        if successful_count % 5 == 0:
                            logger.info(f"✅ Progress: {successful_count} articles crawled successfully")
                    
                    # Add small delay to be respectful
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.warning(f"Failed to crawl {article_url}: {e}")
                    results.append({
                        "url": article_url,
                        "error": str(e),
                        "success": False
                    })
            
            logger.info(f"✅ Auto-crawl completed: {successful_count}/{len(results)} articles processed successfully")
            
            # Return results even if some failed
            if not results:
                return [{"error": "No articles could be crawled successfully", "success": False}]
            
            return results
            
        except Exception as e:
            logger.error(f"Auto-crawl failed for {url}: {e}")
            return [{"error": str(e), "success": False}]
    
    async def _discover_article_urls(self, base_url: str, analysis: Dict[str, Any], 
                                   max_articles: int) -> List[str]:
        """Discover article URLs based on AI analysis"""
        
        try:
            # Use analysis to determine crawling strategy
            strategy = analysis['analysis']['crawling_strategy']
            confidence = analysis['analysis'].get('confidence', 'low')
            
            logger.info(f"🔍 Using strategy: {strategy} (confidence: {confidence})")
            
            article_urls = []
            
            # Try different strategies based on confidence
            if strategy == 'sitemap' and confidence in ['high', 'medium']:
                logger.info("📋 Trying sitemap strategy...")
                article_urls = await self._crawl_sitemap(base_url)
                if article_urls:
                    logger.info(f"✅ Sitemap strategy found {len(article_urls)} URLs")
                    return article_urls[:max_articles]
            
            if strategy == 'category_pages' or not article_urls:
                logger.info("📂 Trying category pages strategy...")
                article_urls = await self._crawl_category_pages(base_url, analysis)
                if article_urls:
                    logger.info(f"✅ Category pages strategy found {len(article_urls)} URLs")
                    return article_urls[:max_articles]
            
            # Always try generic as fallback
            logger.info("🌐 Trying generic strategy...")
            article_urls = await self._crawl_generic(base_url, max_articles)
            if article_urls:
                logger.info(f"✅ Generic strategy found {len(article_urls)} URLs")
                return article_urls
            
            # If all strategies failed, try homepage again with different approach
            logger.info("🏠 Trying homepage deep crawl...")
            article_urls = await self._crawl_homepage_deep(base_url, max_articles)
            if article_urls:
                logger.info(f"✅ Homepage deep crawl found {len(article_urls)} URLs")
                return article_urls
                
        except Exception as e:
            logger.warning(f"Article discovery failed: {e}")
        
        # Final fallback
        logger.warning("⚠️ All discovery strategies failed, returning empty list")
        return []
    
    async def _crawl_sitemap(self, base_url: str) -> List[str]:
        """Crawl sitemap for article URLs"""
        sitemap_urls = [
            f"{base_url}/sitemap.xml",
            f"{base_url}/sitemap_index.xml",
            f"{base_url}/sitemap-news.xml"
        ]
        
        article_urls = []
        for sitemap_url in sitemap_urls:
            try:
                async with aiohttp.ClientSession(
                    connector=aiohttp.TCPConnector(ssl=self.ssl_context),
                    headers=self.headers
                ) as session:
                    async with session.get(sitemap_url, timeout=10) as response:
                        if response.status == 200:
                            content = await response.text()
                            # Simple XML parsing for URLs
                            urls = re.findall(r'<loc>(.*?)</loc>', content)
                            article_urls.extend(urls)
            except:
                continue
        
        return article_urls
    
    async def _crawl_category_pages(self, base_url: str, analysis: Dict[str, Any]) -> List[str]:
        """Crawl category pages for articles"""
        article_urls = []
        
        # Use navigation links from analysis
        nav_links = analysis.get('nav_links', [])
        
        for nav_link in nav_links[:5]:  # Limit to 5 category pages
            try:
                async with aiohttp.ClientSession(
                    connector=aiohttp.TCPConnector(ssl=self.ssl_context),
                    headers=self.headers
                ) as session:
                    async with session.get(nav_link, timeout=15) as response:
                        if response.status == 200:
                            html = await response.text()
                            soup = BeautifulSoup(html, 'html.parser')
                            
                            # Find article links on category page
                            links = soup.find_all('a', href=True)
                            for link in links:
                                href = link.get('href')
                                if href and self._looks_like_article_url(href):
                                    full_url = urljoin(nav_link, href)
                                    article_urls.append(full_url)
            except:
                continue
        
        return list(set(article_urls))
    
    async def _crawl_generic(self, base_url: str, max_articles: int) -> List[str]:
        """Generic crawling strategy"""
        try:
            async with aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=self.ssl_context),
                headers=self.headers
            ) as session:
                async with session.get(base_url, timeout=15) as response:
                    if response.status == 200:
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        article_urls = []
                        links = soup.find_all('a', href=True)
                        
                        for link in links:
                            href = link.get('href')
                            if href and self._looks_like_article_url(href):
                                full_url = urljoin(base_url, href)
                                article_urls.append(full_url)
                        
                        return list(set(article_urls))[:max_articles]
        except:
            return []
    
    async def _crawl_homepage_deep(self, base_url: str, max_articles: int) -> List[str]:
        """Deep crawl homepage with more aggressive link extraction"""
        try:
            async with aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=self.ssl_context),
                headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=20)
            ) as session:
                async with session.get(base_url) as response:
                    if response.status == 200:
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        article_urls = []
                        links = soup.find_all('a', href=True)
                        
                        for link in links:
                            href = link.get('href')
                            if href:
                                full_url = urljoin(base_url, href)
                                
                                # More lenient article detection
                                if self._looks_like_article_url_relaxed(full_url):
                                    article_urls.append(full_url)
                        
                        return list(set(article_urls))[:max_articles]
        except:
            return []
    
    async def _crawl_single_article(self, article_url: str, analysis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Crawl a single article using AI-determined strategy"""
        try:
            # Validate URL
            if not self._is_valid_url(article_url):
                logger.warning(f"Invalid article URL: {article_url}")
                return None
            
            async with aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=self.ssl_context),
                headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as session:
                async with session.get(article_url, allow_redirects=True) as response:
                    if response.status != 200:
                        logger.warning(f"HTTP {response.status} for {article_url}")
                        if response.status == 403:
                            logger.warning(f"Bot blocked (403) for {article_url}")
                        elif response.status == 429:
                            logger.warning(f"Rate limited (429) for {article_url}")
                        return None
                    
                    html = await response.text()
                    
                    # Check if we got valid content
                    if len(html) < 500:
                        logger.warning(f"Article {article_url} returned too little content")
                        return None
                    
                    # Check for bot detection in article content
                    bot_detection_indicators = [
                        "access denied", "blocked", "forbidden", "bot detected",
                        "captcha", "cloudflare", "security check", "rate limit",
                        "temporarily blocked", "suspicious activity"
                    ]
                    
                    html_lower = html.lower()
                    for indicator in bot_detection_indicators:
                        if indicator in html_lower:
                            logger.warning(f"Bot detection in article {article_url}: {indicator}")
                            return None
                    
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Extract content using AI-determined selectors
                    content_selectors = analysis['analysis'].get('content_selectors', ['article', '.content'])
                    content = self._extract_content(soup, content_selectors)
                    
                    if not content or len(content) < 200:
                        logger.warning(f"Article {article_url} has insufficient content")
                        return None
                    
                    # Extract date
                    date_extraction = analysis['analysis'].get('date_extraction', 'url_or_meta')
                    published_date = self._extract_date(soup, article_url, date_extraction)
                    
                    # Extract title
                    title = self._extract_title(soup)
                    
                    # Validate that we have at least a title or content
                    if not title and len(content) < 500:
                        logger.warning(f"Article {article_url} has no title and insufficient content")
                        return None
                    
                    return {
                        'url': article_url,
                        'title': title or "No title available",
                        'content': content,
                        'published_date': published_date,
                        'source': urlparse(article_url).netloc,
                        'success': True
                    }
                    
        except asyncio.TimeoutError:
            logger.warning(f"Timeout crawling article {article_url}")
            return None
        except aiohttp.ClientError as e:
            logger.warning(f"Network error crawling article {article_url}: {e}")
            if "403" in str(e):
                logger.warning(f"Bot blocked while crawling {article_url}")
            elif "429" in str(e):
                logger.warning(f"Rate limited while crawling {article_url}")
            return None
        except Exception as e:
            logger.warning(f"Failed to crawl article {article_url}: {e}")
            return None
    
    async def _crawl_single_article_with_retry(self, article_url: str, analysis: Dict[str, Any], max_retries: int = 2) -> Optional[Dict[str, Any]]:
        """Crawl a single article with retry logic"""
        
        for attempt in range(max_retries + 1):
            try:
                result = await self._crawl_single_article(article_url, analysis)
                if result:
                    return result
                
                # If no result, try again with different strategy
                if attempt < max_retries:
                    logger.info(f"Retrying article {article_url} (attempt {attempt + 1})")
                    await asyncio.sleep(1)  # Wait before retry
                    
            except Exception as e:
                if attempt < max_retries:
                    logger.warning(f"Attempt {attempt + 1} failed for {article_url}: {e}")
                    await asyncio.sleep(1)
                else:
                    logger.error(f"All attempts failed for {article_url}: {e}")
        
        return None
    
    def _extract_content(self, soup: BeautifulSoup, selectors: List[str]) -> str:
        """Extract main content using provided selectors"""
        for selector in selectors:
            elements = soup.select(selector)
            for element in elements:
                # Remove script and style elements
                for script in element(["script", "style"]):
                    script.decompose()
                
                text = element.get_text(strip=True)
                if len(text) > 200:  # Minimum content length
                    return text
        
        # Fallback: try to find content in paragraphs
        paragraphs = soup.find_all('p')
        content = ' '.join([p.get_text(strip=True) for p in paragraphs])
        return content if len(content) > 200 else ""
    
    def _extract_date(self, soup: BeautifulSoup, url: str, method: str) -> str:
        """Extract publication date"""
        try:
            if method == 'url_or_meta':
                # Try URL first
                url_date_match = re.search(r'/(\d{4})/(\d{2})/(\d{2})/', url)
                if url_date_match:
                    year, month, day = url_date_match.groups()
                    return f"{year}-{month}-{day}"
                
                # Try meta tags
                meta_selectors = [
                    'meta[property="article:published_time"]',
                    'meta[name="pubdate"]',
                    'meta[name="date"]',
                    'time[datetime]'
                ]
                
                for selector in meta_selectors:
                    element = soup.select_one(selector)
                    if element:
                        content = element.get('content') or element.get('datetime')
                        if content:
                            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', content)
                            if date_match:
                                return date_match.group(1)
            
            return ""
        except:
            return ""
    
    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract article title"""
        try:
            # Try h1 first
            h1 = soup.find('h1')
            if h1:
                return h1.get_text(strip=True)
            
            # Try title tag
            title = soup.find('title')
            if title:
                return title.get_text(strip=True)
            
            return ""
        except:
            return ""

    def _looks_like_article_url_relaxed(self, url: str) -> bool:
        """More lenient article URL detection"""
        try:
            parsed = urlparse(url)
            path = parsed.path.strip('/')
            
            # Must have some path
            if not path or len(path) < 5:
                return False
            
            # Check for date patterns (more flexible)
            if re.search(r'\d{4}', url):
                return True
            
            # Check for article-like patterns (more flexible)
            article_patterns = [
                r'/article', r'/post', r'/news', r'/story',
                r'/blog', r'/content', r'/entry', r'/feature',
                r'/read', r'/view', r'/detail'
            ]
            
            for pattern in article_patterns:
                if re.search(pattern, url, re.IGNORECASE):
                    return True
            
            # Check for long slug
            path_parts = path.split('/')
            if len(path_parts) >= 2:
                last_part = path_parts[-1]
                if len(last_part) > 15:  # More lenient
                    return True
            
            return False
        except:
            return False

# Global instance
ai_auto_discovery = AIAutoDiscovery()

async def auto_crawl_website_async(url: str, max_articles: int = 20) -> List[Dict[str, Any]]:
    """Async wrapper for auto-crawling website"""
    return await ai_auto_discovery.auto_crawl_website(url, max_articles)

def auto_crawl_website(url: str, max_articles: int = 20) -> List[Dict[str, Any]]:
    """Sync wrapper for auto-crawling website"""
    return asyncio.run(auto_crawl_website_async(url, max_articles)) 