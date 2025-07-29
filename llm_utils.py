import requests
from bs4 import BeautifulSoup
import json
import re
import os
import logging
from datetime import datetime, timedelta, date
import openai
import config
import validators
from urllib.parse import urlparse
from thefuzz import fuzz

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configure OpenAI
openai.api_key = config.OPENAI_API_KEY
openai.api_base = config.LLM_API_URL

def is_valid_url(url):
    """Check if URL is valid"""
    return validators.url(url)

def safe_parse_json(content):
    """Parse JSON safely, handle cases where format is incorrect"""
    try:
        return json.loads(content)
    except Exception as e:
        # Try to find JSON in content
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                logger.warning(f"JSON parse error (regex fallback failed): {e}\nContent: {content[:500]}...")
                return None
        logger.warning(f"JSON parse error (no JSON found): {e}\nContent: {content[:500]}...")
        return None

def normalize_domain(url):
    """Extract normalized domain from URL, handle special TLDs"""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ''
        hostname = hostname.replace('www.', '')
        parts = hostname.split('.')
        
        # Handle special TLDs like .ai, .energy, .xyz
        if len(parts) > 2:
            # Example: sub.example.ai -> example.ai
            return '.'.join(parts[-2:])
        elif len(parts) == 2:
            return '.'.join(parts)
        else:
            return parts[0] if parts else ''
    except Exception:
        return ''

def company_name_matches_domain(company_name, domain):
    """Fuzzy match company name with domain"""
    if not company_name or not domain:
        return 0
    
    # Normalize
    norm_company = re.sub(r'[^a-z0-9]', '', company_name.lower())
    norm_domain = re.sub(r'[^a-z0-9]', '', domain.lower())
    
    # Calculate score
    score = fuzz.partial_ratio(norm_company, norm_domain)
    return score

def llm_prompt(prompt_text, max_tokens=1024, temperature=0.1, model=None):
    """Call common LLM, easy to switch models"""
    if model is None:
        model = config.LLM_MODEL_ID
    
    try:
        response = openai.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt_text}],
            max_tokens=max_tokens,
            temperature=temperature
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"LLM API error: {e}")
        return None

def has_funding_keywords(text):
    """Check funding keywords before calling LLM"""
    # More comprehensive funding keywords to avoid false positives
    funding_keywords = [
        # Direct funding terms
        'raises', 'raised', 'funding round', 'investment round', 'series a', 'series b', 'series c',
        'seed round', 'angel round', 'venture round', 'fundraising', 'capital raise',
        'venture capital', 'angel investment', 'angel investor', 'angel funding',
        'backed by', 'invested in', 'led by', 'co-led by', 'participated in',
        'closes funding', 'announces funding', 'secures funding', 'receives investment',
        'funding led by', 'investment led by', 'round led by',
        
        # Additional funding terms
        'funding', 'investment', 'capital', 'financing', 'funding round', 'investment round',
        'series funding', 'seed funding', 'angel funding', 'venture funding',
        'equity funding', 'debt funding', 'convertible note', 'pre-seed funding',
        'growth funding', 'expansion funding', 'strategic investment',
        
        # Amount patterns (only in funding context)
        'million in funding', 'billion in funding', 'million investment', 'billion investment',
        'million raised', 'billion raised', 'million funding', 'billion funding',
        'million capital', 'billion capital', 'million financing', 'billion financing',
        
        # Investor patterns
        'investors', 'venture capitalists', 'vc firms', 'angel investors',
        'private equity', 'investment firms', 'fund managers',
        
        # Funding announcement patterns
        'announces', 'announced', 'announcement', 'closes', 'closed', 'closing',
        'secures', 'secured', 'receives', 'received', 'obtains', 'obtained',
        
        # Additional context
        'funding round', 'investment round', 'capital round', 'equity round',
        'pre-seed', 'seed funding', 'series funding', 'growth funding',
        'strategic investment', 'equity investment', 'debt funding', 'convertible note',
        
        # More flexible patterns
        'funding', 'investment', 'capital', 'financing', 'backing', 'support',
        'funded', 'invested', 'backed', 'supported', 'financed',
        
        # Additional funding-related terms
        'round of funding', 'funding announcement', 'investment announcement',
        'capital injection', 'equity round', 'debt round', 'convertible round',
        'bridge round', 'extension round', 'follow-on round',
        'initial funding', 'seed capital', 'startup funding', 'tech funding'
    ]
    
    text_lower = text.lower()
    
    # Check for funding keywords
    found_keywords = []
    for keyword in funding_keywords:
        if keyword in text_lower:
            found_keywords.append(keyword)
    
    # If no keywords found, return False
    if not found_keywords:
        return False
    
    # Additional context check for common false positives
    false_positive_indicators = [
        'competition', 'challenge', 'contest', 'award', 'grant', 'prize',
        'million users', 'billion users', 'million downloads', 'billion downloads',
        'million revenue', 'billion revenue', 'million valuation', 'billion valuation',
        'partnership', 'deal', 'agreement', 'contract', 'service', 'product launch',
        'acquisition', 'merger', 'ipo', 'initial public offering', 'public listing'
    ]
    
    # Check if there are false positive indicators
    has_false_positive = any(indicator in text_lower for indicator in false_positive_indicators)
    
    if has_false_positive:
        # Only return True if there are very specific funding terms AND no false positive context
        specific_funding_terms = [
            'raises', 'raised', 'funding round', 'investment round', 'series a', 'series b', 'series c',
            'seed round', 'angel round', 'venture round', 'fundraising', 'capital raise',
            'venture capital', 'angel investment', 'backed by', 'invested in', 'led by'
        ]
        
        # Check if there are specific funding terms
        has_specific_funding = any(term in text_lower for term in specific_funding_terms)
        
        # If there are false positives but no specific funding terms, return False
        if not has_specific_funding:
            return False
        
        # If there are both false positives and specific funding terms, 
        # check if the context is clearly about funding vs other business activities
        funding_context_indicators = [
            'raises', 'raised', 'funding', 'investment', 'venture capital', 'angel investment',
            'series a', 'series b', 'series c', 'seed round', 'angel round', 'led by'
        ]
        
        # Count funding context indicators
        funding_context_count = sum(1 for indicator in funding_context_indicators if indicator in text_lower)
        
        # Only return True if there are multiple funding context indicators
        return funding_context_count >= 2
    
    # If no false positives, check if there are specific funding terms
    specific_funding_terms = [
        'raises', 'raised', 'funding round', 'investment round', 'series a', 'series b', 'series c',
        'seed round', 'angel round', 'venture round', 'fundraising', 'capital raise',
        'venture capital', 'angel investment', 'backed by', 'invested in', 'led by'
    ]
    
    # If there are specific funding terms, return True
    if any(term in text_lower for term in specific_funding_terms):
        return True
    
    # For other keywords, check if there are multiple funding-related terms
    funding_related_terms = [
        'funding', 'investment', 'capital', 'financing', 'venture capital', 'angel investment',
        'investors', 'venture capitalists', 'vc firms', 'angel investors'
    ]
    
    funding_related_count = sum(1 for term in funding_related_terms if term in text_lower)
    
    # Only return True if there are multiple funding-related terms
    return funding_related_count >= 2

def is_funding_article_llm(article_text):
    """
    Check if article is about funding/investment.
    Optimized: use keyword check before calling LLM
    """
    # 1. Keyword check first
    if not has_funding_keywords(article_text):
        return False
    
    # 2. Call LLM if keywords found
    prompt = (
        "You are a startup news analyst. "
        "Determine if this article is SPECIFICALLY about a company raising funding or receiving investment.\n\n"
        "CRITICAL: Only return TRUE if the article is about:\n"
        "- A company raising money (Series A, B, C, seed, etc.)\n"
        "- A company receiving investment from VCs or investors\n"
        "- A company closing a funding round\n"
        "- A company announcing fundraising\n\n"
        "Return FALSE if the article is about:\n"
        "- General business news, product launches, partnerships\n"
        "- Awards, grants, or non-investment funding\n"
        "- Company performance, revenue, or other business metrics\n"
        "- Technology news, AI competitions, or other non-funding topics\n\n"
        "IMPORTANT: Return ONLY a JSON object with this exact format:\n"
        "{\"is_funding\": true/false, \"reason\": \"brief explanation\"}\n\n"
        f"Article:\n{article_text[:3000]}..."
    )
    
    content = llm_prompt(prompt, max_tokens=256)
    if not content:
        logger.error("LLM returned no content for funding article check")
        return False
    
    result = safe_parse_json(content)
    if not result:
        logger.error(f"Could not parse JSON from LLM content. Raw content: {content[:1000]}...")
        return False
    
    if result and result.get('is_funding'):
        logger.info(f"Funding article detected: {result.get('reason', '')}")
        return True
    
    return False

def extract_candidate_paragraphs(article_text):
    """
    Return the first 2 paragraphs (split by double newlines or periods) as candidate text for LLM extraction.
    """
    if not article_text:
        return ""
    paras = [p.strip() for p in article_text.split('\n') if p.strip()]
    if len(paras) >= 2:
        return '\n'.join(paras[:2])
    # fallback: try splitting by period
    sentences = article_text.split('.')
    return '.'.join(sentences[:4])

def extract_company_name_and_raised_date_llm(article_text, min_date, max_date):
    """
    Extract company name and funding date from article.
    Optimized: combined with extract_funding_info_llm
    """
    prompt = (
        "You are a startup news analyst. "
        "Extract the following information from this funding article:\n\n"
        "1. Main company name mentioned\n"
        "2. Funding announcement date (if any)\n"
        "3. Funding amount (if any)\n"
        "4. Funding round type (if any)\n\n"
        "IMPORTANT: Return ONLY a JSON object with this exact format:\n"
        "{\n"
        '  "company_name": "company name",\n'
        '  "raised_date": "YYYY-MM-DD",\n'
        '  "amount": "amount",\n'
        '  "round_type": "round type"\n'
        "}\n\n"
        f"Date range: {min_date} to {max_date}\n"
        f"Article:\n{article_text[:2000]}..."
    )
    
    content = llm_prompt(prompt, max_tokens=512)
    if not content:
        logger.error("LLM returned no content for company extraction")
        return None
    
    result = safe_parse_json(content)
    if not result:
        logger.error(f"Could not parse JSON from LLM content. Raw content: {content[:1000]}...")
        return None
    
    if result:
        logger.info(f"Extracted company: {result.get('company_name', '')}")
        return result
    
    return None

def extract_funding_info_llm(article_text):
    """
    Extract funding information using LLM.
    """
    # 1. Extract candidate paragraphs
    candidate_text = extract_candidate_paragraphs(article_text)
    # 2. Clear prompt
    prompt = (
        "Extract the following information from this text:\n"
        "1. Company name that was newly founded or just raised funding\n"
        "2. Official website (if mentioned in text, leave empty if not found)\n"
        "3. Company LinkedIn link (if not in text, leave empty)\n"
        "4. Date company raised funding (if any, format YYYY-MM-DD, leave empty if not found)\n"
        "IMPORTANT: Return ONLY a JSON object with this exact format:\n"
        "{\n"
        '  "company_name": "company name",\n'
        '  "website": "website url",\n'
        '  "linkedin": "linkedin url",\n'
        '  "raised_date": "YYYY-MM-DD"\n'
        "}\n\n"
        f"Text:\n{candidate_text}\n\nJSON:"
    )
    
    content = llm_prompt(prompt, max_tokens=512)
    if not content:
        logger.error("LLM returned no content for funding info extraction")
        return None
    
    result = safe_parse_json(content)
    if not result:
        logger.error(f"Could not parse JSON from LLM content. Raw content: {content[:1000]}...")
        return None
    
    # 3. Fallback search nếu thiếu website/linkedin
    if result:
        company_name = result.get('company_name', '').strip()
        # Fallback website
        if not result.get('website') and company_name:
            from search_utils import find_company_website
            result['website'] = find_company_website(company_name)
        # Fallback linkedin
        if not result.get('linkedin') and company_name:
            from search_utils import find_company_linkedin
            result['linkedin'] = find_company_linkedin(company_name)
    return result

def extract_company_info_llm(article_text, links_context=None):
    """
    Extract company information, website, LinkedIn.
    Optimized: combine all info in one call
    """
    links_info = ""
    if links_context:
        links_info = f"\nLinks in article: {links_context}"
    
    prompt = (
        "You are a startup analyst. Extract information from this article:\n\n"
        "1. Main company name\n"
        "2. Official website (if mentioned in article or can be inferred)\n"
        "3. Official LinkedIn (if mentioned in article or can be inferred)\n"
        "4. If website not found, guess 3 possible domains (e.g., alix.com, alix.ai, getalix.com)\n"
        "5. If LinkedIn not found, guess possible LinkedIn URL\n\n"
        "IMPORTANT: Return ONLY a JSON object with this exact format:\n"
        "{\n"
        '  "company_name": "company name",\n'
        '  "website": "official website",\n'
        '  "website_guesses": ["domain1", "domain2", "domain3"],\n'
        '  "linkedin": "official linkedin",\n'
        '  "linkedin_guess": "linkedin guess",\n'
        '  "confidence": "high/medium/low",\n'
        '  "reasoning": "explanation"\n'
        "}\n\n"
        f"Article:\n{article_text[:2000]}...{links_info}"
    )
    
    content = llm_prompt(prompt, max_tokens=1024)
    if not content:
        logger.error("LLM returned no content for company info extraction")
        return None
    
    result = safe_parse_json(content)
    if not result:
        logger.error(f"Could not parse JSON from LLM content. Raw content: {content[:1000]}...")
        return None
    
    if result:
        logger.info(f"LLM extracted: {result.get('company_name', '')} | confidence: {result.get('confidence', '')}")
        return result
    
    return None

def fetch_page_content(url, max_chars=1000):
    """Fetch webpage content to verify"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Get text from body
        body = soup.find('body')
        if body:
            text = body.get_text(separator=' ', strip=True)
            return text[:max_chars] + '...' if len(text) > max_chars else text
        
        return ''
    except Exception as e:
        logger.warning(f"Error fetching content for {url}: {e}")
        return ''

def verify_url_with_llm(url, company_name, url_type="website", context=None):
    """
    Verify URL using LLM with context from webpage content
    """
    # Get context if not provided
    if not context:
        context = fetch_page_content(url, max_chars=500)
    
    context_info = f"\nPage content: {context}" if context else ""
    
    prompt = (
        f"Check if this URL is the official {url_type} of company '{company_name}'?\n\n"
        f"URL: {url}\n"
        f"Company: {company_name}\n"
        f"Type: {url_type}{context_info}\n\n"
        "Consider:\n"
        "- Does domain match company name?\n"
        "- Is page content related to the company?\n"
        "- Is this the official page?\n\n"
        "Return JSON: {\"is_valid\": true/false, \"confidence\": \"high/medium/low\", \"reason\": \"explanation\"}"
    )
    
    content = llm_prompt(prompt, max_tokens=256, model="gpt-3.5-turbo-0125")
    if not content:
        return False
    
    result = safe_parse_json(content)
    if result:
        is_valid = result.get('is_valid', False)
        confidence = result.get('confidence', 'low')
        reason = result.get('reason', '')
        
        logger.info(f"[URL VERIFICATION] {company_name} -> {url} | valid: {is_valid} | confidence: {confidence} | reason: {reason}")
        
        return is_valid
    
    return False

def normalize_company_name_for_search(company_name):
    """Normalize company name for search"""
    if not company_name:
        return ""
    
    # Remove unnecessary words
    stop_words = ['inc', 'llc', 'ltd', 'corp', 'corporation', 'company', 'co']
    words = company_name.lower().split()
    filtered_words = [w for w in words if w not in stop_words]
    
    return ' '.join(filtered_words).strip()

def find_company_website_llm(company_name, context=""):
    """
    Find company website using LLM.
    """
    prompt = (
        f"What is the official website of the startup company named '{company_name}'{f', {context}' if context else ''}? Only return the URL, nothing else. If you are not sure, return 'unknown'."
    )
    
    content = llm_prompt(prompt, max_tokens=32)
    if not content:
        return '', True
    
    url = content.strip()
    if is_valid_url(url):
        logger.info(f"[DEBUG][LLM WEBSITE] {company_name} | {url}")
        return url, False  # False = ambiguous
    if url.lower() != 'unknown':
        logger.info(f"[DEBUG][LLM WEBSITE GUESS] {company_name} | {url}")
        return url, True  # True = ambiguous
    return '', True

def find_company_linkedin_llm(company_name, context=""):
    """
    Find company LinkedIn using LLM.
    """
    prompt = (
        f"What is the LinkedIn page URL of the startup company named '{company_name}'{f', {context}' if context else ''}? Only return the URL, nothing else. If you are not sure, return 'unknown'."
    )
    
    content = llm_prompt(prompt, max_tokens=32)
    if not content:
        return '', True
    
    url = content.strip()
    if is_valid_url(url) and "linkedin.com/company" in url:
        logger.info(f"[DEBUG][LLM LINKEDIN] {company_name} | {url}")
        return url, False
    if url.lower() != 'unknown':
        logger.info(f"[DEBUG][LLM LINKEDIN GUESS] {company_name} | {url}")
        return url, True
    return '', True

def is_negative_news(article_text):
    """
    Check if article contains negative news keywords.
    """
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

def extract_funding_amount_llm(article_text):
    """
    Extract funding amount from article text using LLM
    """
    prompt = (
        "Extract the funding amount from this article. "
        "Look for specific amounts mentioned in the context of funding, investment, or raising money.\n\n"
        "IMPORTANT: Return ONLY a JSON object with this exact format:\n"
        "{\n"
        '  "amount": "amount in USD (e.g., $10M, $50 million)",\n'
        '  "currency": "USD",\n'
        '  "confidence": "high/medium/low"\n'
        "}\n\n"
        f"Article:\n{article_text[:1500]}..."
    )
    
    content = llm_prompt(prompt, max_tokens=256)
    if not content:
        logger.error("LLM returned no content for funding amount extraction")
        return None
    
    result = safe_parse_json(content)
    if not result:
        logger.error(f"Could not parse JSON from LLM content. Raw content: {content[:1000]}...")
        return None
    
    return result

def extract_funding_round_type_llm(article_text):
    """
    Extract funding round type from article text using LLM
    """
    prompt = (
        "Extract the funding round type from this article. "
        "Look for terms like Series A, Series B, Series C, Seed, Pre-seed, etc.\n\n"
        "IMPORTANT: Return ONLY a JSON object with this exact format:\n"
        "{\n"
        '  "round_type": "round type (e.g., Series A, Seed, Pre-seed)",\n'
        '  "confidence": "high/medium/low"\n'
        "}\n\n"
        f"Article:\n{article_text[:1500]}..."
    )
    
    content = llm_prompt(prompt, max_tokens=256)
    if not content:
        logger.error("LLM returned no content for funding round extraction")
        return None
    
    result = safe_parse_json(content)
    if not result:
        logger.error(f"Could not parse JSON from LLM content. Raw content: {content[:1000]}...")
        return None
    
    return result

def validate_company_name_llm(company_name, article_text):
    """
    Validate if the extracted company name is correct using LLM
    """
    prompt = (
        f"Validate if '{company_name}' is the correct company name mentioned in this article.\n\n"
        "Consider:\n"
        "- Is this the main company being discussed?\n"
        "- Is this the company that raised funding?\n"
        "- Are there any other companies mentioned that might be more relevant?\n\n"
        "IMPORTANT: Return ONLY a JSON object with this exact format:\n"
        "{\n"
        '  "is_valid": true/false,\n'
        '  "corrected_name": "correct name if different",\n'
        '  "confidence": "high/medium/low",\n'
        '  "reason": "explanation"\n'
        "}\n\n"
        f"Article:\n{article_text[:1500]}..."
    )
    
    content = llm_prompt(prompt, max_tokens=512)
    if not content:
        logger.error("LLM returned no content for company name validation")
        return None
    
    result = safe_parse_json(content)
    if not result:
        logger.error(f"Could not parse JSON from LLM content. Raw content: {content[:1000]}...")
        return None
    
    return result

def extract_multiple_companies_llm(article_text):
    """
    Extract multiple companies if the article mentions more than one company
    """
    prompt = (
        "Extract all companies mentioned in this article that are related to funding or investment.\n\n"
        "IMPORTANT: Return ONLY a JSON object with this exact format:\n"
        "{\n"
        '  "companies": [\n'
        '    {\n'
        '      "name": "company name",\n'
        '      "role": "investor/startup/other",\n'
        '      "funding_amount": "amount if startup",\n'
        '      "round_type": "round type if startup"\n'
        '    }\n'
        '  ]\n'
        "}\n\n"
        f"Article:\n{article_text[:2000]}..."
    )
    
    content = llm_prompt(prompt, max_tokens=1024)
    if not content:
        logger.error("LLM returned no content for multiple companies extraction")
        return None
    
    result = safe_parse_json(content)
    if not result:
        logger.error(f"Could not parse JSON from LLM content. Raw content: {content[:1000]}...")
        return None
    
    return result 