import time
import random
import functools
import logging
import requests
import openai
from typing import Callable, Any, Optional

logger = logging.getLogger(__name__)

def exponential_backoff_retry(
    max_retries: int = 3, 
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exceptions: tuple = (Exception,)
):
    """
    Decorator for exponential backoff retry mechanism.
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay between retries (seconds)
        max_delay: Maximum delay between retries (seconds)
        exceptions: Tuple of exceptions to catch and retry
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        logger.error(f"Function {func.__name__} failed after {max_retries} retries: {e}")
                        raise
                    
                    # Calculate delay with exponential backoff
                    delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)
                    logger.warning(f"Function {func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}): {e}. Retrying in {delay:.2f}s...")
                    time.sleep(delay)
            
            # This should never be reached, but just in case
            raise last_exception
        
        return wrapper
    return decorator

def fetch_with_retry(url: str, headers: dict = None, timeout: int = 30, max_retries: int = 3) -> requests.Response:
    """
    Fetch URL with retry mechanism for HTTP requests.
    
    Args:
        url: URL to fetch
        headers: HTTP headers
        timeout: Request timeout in seconds
        max_retries: Maximum number of retry attempts
    
    Returns:
        requests.Response object
    """
    @exponential_backoff_retry(max_retries=max_retries, exceptions=(requests.RequestException,))
    def _fetch():
        return requests.get(url, headers=headers, timeout=timeout)
    
    return _fetch()

def llm_call_with_retry(
    prompt: str,
    max_tokens: int = 512,
    temperature: float = 0,
    model: Optional[str] = None,
    max_retries: int = 3
) -> Optional[str]:
    """
    Call LLM with retry mechanism
    """
    from .. import config
    
    @exponential_backoff_retry(
        max_retries=max_retries,
        base_delay=2.0,
        exceptions=(Exception,)
    )
    def _llm_call():
        if model is None:
            model_id = config.LLM_MODEL_ID
        else:
            model_id = model
            
        # Use old initialization method to avoid proxies error
        openai.api_key = config.OPENAI_API_KEY
        response = openai.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature
        )
        return response.choices[0].message.content.strip()
    
    try:
        return _llm_call()
    except Exception as e:
        logger.error(f"LLM call failed after retries: {e}")
        return None

def safe_request(url: str, headers: dict = None, timeout: int = 30) -> Optional[requests.Response]:
    """
    Safe HTTP request with error handling and logging.
    
    Args:
        url: URL to request
        headers: HTTP headers
        timeout: Request timeout in seconds
    
    Returns:
        requests.Response or None if failed
    """
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response
    except requests.RequestException as e:
        logger.error(f"Request failed for {url}: {e}")
        return None 