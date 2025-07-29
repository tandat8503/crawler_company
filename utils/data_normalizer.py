import re
import logging
from datetime import datetime, date
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

def normalize_currency_amount(amount_str: str) -> Tuple[str, str]:
    """
    Normalize currency amount to standard format.
    Returns: (normalized_amount, currency_code)
    
    Examples:
    - "$6.6 million" -> ("6600000", "USD")
    - "€1.5M" -> ("1500000", "EUR") 
    - "£2.3 billion" -> ("2300000000", "GBP")
    - "500K" -> ("500000", "USD")
    """
    if not amount_str or not isinstance(amount_str, str):
        return ("", "")
    
    amount_str = amount_str.strip()
    
    # Currency mapping
    currency_map = {
        '$': 'USD',
        '€': 'EUR', 
        '£': 'GBP',
        '¥': 'JPY',
        '₹': 'INR',
        '₿': 'BTC'
    }
    
    # Extract currency
    currency = "USD"  # Default
    for symbol, code in currency_map.items():
        if symbol in amount_str:
            currency = code
            amount_str = amount_str.replace(symbol, '').strip()
            break
    
    # Remove common words
    amount_str = re.sub(r'\b(dollars?|euros?|pounds?|yen|rupees?|bitcoin)\b', '', amount_str, flags=re.IGNORECASE)
    amount_str = amount_str.strip()
    
    # Handle different number formats
    try:
        # Handle "X.X million/billion/thousand"
        multipliers = {
            'thousand': 1000,
            'k': 1000,
            'million': 1000000,
            'm': 1000000,
            'billion': 1000000000,
            'b': 1000000000,
            'trillion': 1000000000000,
            't': 1000000000000
        }
        
        # Find multiplier
        multiplier = 1
        for word, mult in multipliers.items():
            if word in amount_str.lower():
                multiplier = mult
                amount_str = re.sub(rf'\b{word}\b', '', amount_str, flags=re.IGNORECASE)
                break
        
        # Extract numeric part
        numeric_match = re.search(r'[\d,]+\.?\d*', amount_str)
        if numeric_match:
            numeric_str = numeric_match.group().replace(',', '')
            base_amount = float(numeric_str)
            final_amount = int(base_amount * multiplier)
            return (str(final_amount), currency)
        
        # Try direct number parsing
        numeric_str = re.sub(r'[^\d.]', '', amount_str)
        if numeric_str:
            base_amount = float(numeric_str)
            final_amount = int(base_amount * multiplier)
            return (str(final_amount), currency)
            
    except (ValueError, TypeError) as e:
        logger.warning(f"Error parsing amount: {amount_str} - {e}")
    
    return ("", currency)

def normalize_date(date_str: str) -> str:
    """
    Normalize date string to YYYY-MM-DD format.
    
    Examples:
    - "July 23, 2025" -> "2025-07-23"
    - "2025-07-24" -> "2025-07-24"
    - "23/07/2025" -> "2025-07-23"
    - "07-23-2025" -> "2025-07-23"
    """
    if not date_str or not isinstance(date_str, str):
        return ""
    
    date_str = date_str.strip()
    
    # Already in YYYY-MM-DD format
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return date_str
    
    try:
        # Try different date formats
        date_formats = [
            '%B %d, %Y',      # July 23, 2025
            '%b %d, %Y',       # Jul 23, 2025
            '%d/%m/%Y',        # 23/07/2025
            '%m/%d/%Y',        # 07/23/2025
            '%d-%m-%Y',        # 23-07-2025
            '%m-%d-%Y',        # 07-23-2025
            '%Y/%m/%d',        # 2025/07/23
            '%d %B %Y',        # 23 July 2025
            '%d %b %Y',        # 23 Jul 2025
            '%B %d %Y',        # July 23 2025
            '%b %d %Y',        # Jul 23 2025
        ]
        
        for fmt in date_formats:
            try:
                parsed_date = datetime.strptime(date_str, fmt)
                return parsed_date.strftime('%Y-%m-%d')
            except ValueError:
                continue
        
        # Try ISO format with timezone
        if 'T' in date_str or 'Z' in date_str:
            try:
                # Handle ISO format like "2025-07-23T10:30:00Z"
                if 'Z' in date_str:
                    date_str = date_str.replace('Z', '+00:00')
                parsed_date = datetime.fromisoformat(date_str)
                return parsed_date.strftime('%Y-%m-%d')
            except ValueError:
                pass
        
        # Try to extract date from complex strings
        date_patterns = [
            r'(\d{4})-(\d{1,2})-(\d{1,2})',  # YYYY-M-D
            r'(\d{1,2})/(\d{1,2})/(\d{4})',   # M/D/YYYY
            r'(\d{1,2})-(\d{1,2})-(\d{4})',   # M-D-YYYY
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, date_str)
            if match:
                groups = match.groups()
                if len(groups) == 3:
                    if len(groups[0]) == 4:  # YYYY-M-D
                        year, month, day = groups
                    else:  # M/D/YYYY
                        month, day, year = groups
                    
                    # Pad with zeros
                    month = month.zfill(2)
                    day = day.zfill(2)
                    
                    return f"{year}-{month}-{day}"
        
    except Exception as e:
        logger.warning(f"Error parsing date: {date_str} - {e}")
    
    return ""

def normalize_funding_round(round_str: str) -> str:
    """
    Normalize funding round to standard format.
    
    Examples:
    - "Series A" -> "Series A"
    - "seed round" -> "Seed"
    - "pre-seed" -> "Pre-Seed"
    - "Series B" -> "Series B"
    """
    if not round_str or not isinstance(round_str, str):
        return ""
    
    round_str = round_str.strip().lower()
    
    # Standardize common variations
    round_mapping = {
        'seed': 'Seed',
        'seed round': 'Seed',
        'pre-seed': 'Pre-Seed',
        'pre seed': 'Pre-Seed',
        'preseed': 'Pre-Seed',
        'series a': 'Series A',
        'series-a': 'Series A',
        'seriesa': 'Series A',
        'series b': 'Series B',
        'series-b': 'Series B',
        'seriesb': 'Series B',
        'series c': 'Series C',
        'series-c': 'Series C',
        'seriesc': 'Series C',
        'series d': 'Series D',
        'series-d': 'Series D',
        'seriesd': 'Series D',
        'angel': 'Angel',
        'angel round': 'Angel',
        'angel investment': 'Angel',
        'venture': 'Venture',
        'venture round': 'Venture',
        'growth': 'Growth',
        'growth round': 'Growth',
        'bridge': 'Bridge',
        'bridge round': 'Bridge',
        'extension': 'Extension',
        'extension round': 'Extension',
        'follow-on': 'Follow-On',
        'follow on': 'Follow-On',
        'followon': 'Follow-On',
        'ipo': 'IPO',
        'initial public offering': 'IPO',
        'mezzanine': 'Mezzanine',
        'mezzanine round': 'Mezzanine',
        'strategic': 'Strategic',
        'strategic investment': 'Strategic',
        'equity': 'Equity',
        'equity round': 'Equity',
        'debt': 'Debt',
        'debt round': 'Debt',
        'convertible note': 'Convertible Note',
        'convertible': 'Convertible Note',
        'note': 'Convertible Note'
    }
    
    return round_mapping.get(round_str, round_str.title())

def normalize_company_name(name: str) -> str:
    """
    Normalize company name for consistent storage.
    
    Examples:
    - "NetZeroNitrogen Inc." -> "NetZeroNitrogen"
    - "CVector, Inc." -> "CVector"
    - "company-name" -> "Company Name"
    """
    if not name or not isinstance(name, str):
        return ""
    
    name = name.strip()
    
    # Remove common suffixes
    suffixes = [
        ' inc', ' llc', ' ltd', ' corp', ' corporation', ' company', ' co',
        ' group', ' solutions', ' technologies', ' tech', ' systems',
        ' ventures', ' capital', ' partners', ' holdings'
    ]
    
    for suffix in suffixes:
        if name.lower().endswith(suffix):
            name = name[:-len(suffix)].strip()
            break
    
    # Clean up special characters
    name = re.sub(r'[^\w\s-]', '', name)  # Remove special chars except spaces and hyphens
    name = re.sub(r'\s+', ' ', name)  # Normalize spaces
    name = name.strip()
    
    return name

def extract_funding_info_from_text(text: str) -> dict:
    """
    Extract and normalize funding information from text.
    Returns: {
        'amount': '6600000',
        'currency': 'USD', 
        'round_type': 'Seed',
        'date': '2025-07-23'
    }
    """
    result = {
        'amount': '',
        'currency': 'USD',
        'round_type': '',
        'date': ''
    }
    
    if not text:
        return result
    
    # Extract amount patterns
    amount_patterns = [
        r'\$[\d,]+\.?\d*\s*(?:million|billion|thousand|k|m|b)?',
        r'€[\d,]+\.?\d*\s*(?:million|billion|thousand|k|m|b)?',
        r'£[\d,]+\.?\d*\s*(?:million|billion|thousand|k|m|b)?',
        r'[\d,]+\.?\d*\s*(?:million|billion|thousand|k|m|b)\s*(?:dollars?|euros?|pounds?)?',
        r'[\d,]+\.?\d*[kmb]\s*(?:dollars?|euros?|pounds?)?'
    ]
    
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            amount_str = match.group()
            normalized_amount, currency = normalize_currency_amount(amount_str)
            result['amount'] = normalized_amount
            result['currency'] = currency
            break
    
    # Extract round type
    round_patterns = [
        r'(\$[\d,]+\.?\d*\s*(?:million|billion|thousand|k|m|b)?)\s*(seed|pre-seed|series\s*[abcd]|angel|venture|growth|bridge|extension|follow-on|ipo|mezzanine|strategic|equity|debt|convertible\s*note)',
        r'(seed|pre-seed|series\s*[abcd]|angel|venture|growth|bridge|extension|follow-on|ipo|mezzanine|strategic|equity|debt|convertible\s*note)\s*round',
        r'(\$[\d,]+\.?\d*\s*(?:million|billion|thousand|k|m|b)?)\s*round'
    ]
    
    for pattern in round_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            round_str = match.group(1) if len(match.groups()) > 1 else match.group()
            result['round_type'] = normalize_funding_round(round_str)
            break
    
    # Extract date
    date_patterns = [
        r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b',
        r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}\b',
        r'\b\d{4}-\d{2}-\d{2}\b',
        r'\b\d{1,2}/\d{1,2}/\d{4}\b',
        r'\b\d{1,2}-\d{1,2}-\d{4}\b'
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, text)
        if match:
            date_str = match.group()
            normalized_date = normalize_date(date_str)
            if normalized_date:
                result['date'] = normalized_date
                break
    
    return result

def validate_and_normalize_entry(entry: dict) -> dict:
    """
    Validate and normalize a database entry before insertion.
    """
    normalized_entry = entry.copy()
    
    # Normalize company name
    if 'company_name' in normalized_entry:
        normalized_entry['company_name'] = normalize_company_name(normalized_entry['company_name'])
    
    # Normalize amount
    if 'amount_raised' in normalized_entry:
        amount_str = str(normalized_entry['amount_raised'])
        normalized_amount, currency = normalize_currency_amount(amount_str)
        normalized_entry['amount_raised'] = normalized_amount
        normalized_entry['currency'] = currency
    
    # Normalize funding round
    if 'funding_round' in normalized_entry:
        normalized_entry['funding_round'] = normalize_funding_round(normalized_entry['funding_round'])
    
    # Normalize dates
    for date_field in ['raised_date', 'crawl_date']:
        if date_field in normalized_entry:
            date_str = str(normalized_entry[date_field])
            normalized_date = normalize_date(date_str)
            if normalized_date:
                normalized_entry[date_field] = normalized_date
    
    return normalized_entry 