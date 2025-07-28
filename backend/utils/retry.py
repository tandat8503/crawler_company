import time
import random
import functools
import logging
import openai
from typing import Callable, Any, Optional

logger = logging.getLogger(__name__)

def exponential_backoff_retry(
    max_retries: int = 3, 
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """
    Decorator để áp dụng exponential backoff retry cho các hàm
    
    Args:
        max_retries: Số lần retry tối đa
        base_delay: Thời gian delay cơ bản (giây)
        max_delay: Thời gian delay tối đa (giây)
        backoff_factor: Hệ số tăng delay
        exceptions: Tuple các exception cần retry
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
                        raise e
                    
                    # Tính toán delay với exponential backoff
                    delay = min(base_delay * (backoff_factor ** attempt), max_delay)
                    delay += random.uniform(0, 1)  # Thêm jitter
                    
                    logger.warning(
                        f"Function {func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
            
            # Fallback (không bao giờ đến đây)
            raise last_exception
        
        return wrapper
    return decorator

def fetch_with_retry(
    url: str, 
    headers: Optional[dict] = None, 
    timeout: int = 10,
    max_retries: int = 3
) -> 'requests.Response':
    """
    Fetch URL với retry mechanism
    
    Args:
        url: URL cần fetch
        headers: Headers cho request
        timeout: Timeout cho request
        max_retries: Số lần retry tối đa
    
    Returns:
        requests.Response object
    """
    import requests
    
    @exponential_backoff_retry(
        max_retries=max_retries,
        base_delay=1.0,
        exceptions=(requests.RequestException,)
    )
    def _fetch():
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response
    
    return _fetch()

def llm_call_with_retry(
    prompt: str,
    max_tokens: int = 512,
    temperature: float = 0,
    model: Optional[str] = None,
    max_retries: int = 3
) -> Optional[str]:
    """
    Gọi LLM với retry mechanism
    
    Args:
        prompt: Prompt để gửi cho LLM
        max_tokens: Số token tối đa
        temperature: Temperature cho generation
        model: Model ID
        max_retries: Số lần retry tối đa
    
    Returns:
        Response từ LLM hoặc None nếu thất bại
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
            
        # Sử dụng cách khởi tạo cũ để tránh lỗi proxies
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

def safe_request(
    method: str,
    url: str,
    headers: Optional[dict] = None,
    data: Optional[dict] = None,
    timeout: int = 10,
    max_retries: int = 3
) -> Optional['requests.Response']:
    """
    Thực hiện HTTP request an toàn với retry
    
    Args:
        method: HTTP method (GET, POST, etc.)
        url: URL target
        headers: Request headers
        data: Request data
        timeout: Request timeout
        max_retries: Số lần retry tối đa
    
    Returns:
        requests.Response hoặc None nếu thất bại
    """
    import requests
    
    @exponential_backoff_retry(
        max_retries=max_retries,
        base_delay=1.0,
        exceptions=(requests.RequestException,)
    )
    def _request():
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            data=data,
            timeout=timeout
        )
        response.raise_for_status()
        return response
    
    try:
        return _request()
    except Exception as e:
        logger.error(f"Request failed after retries: {method} {url} - {e}")
        return None 