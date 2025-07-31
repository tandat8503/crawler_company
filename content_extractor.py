# file: content_extractor.py
import trafilatura
from utils.logger import logger

def extract_main_content(url: str) -> str:
    """
    Sử dụng Trafilatura để trích xuất nội dung chính từ một URL.
    Đây là cách tiếp cận mạnh mẽ hơn nhiều so với việc dựa vào CSS selectors.

    Args:
        url: URL của bài báo.

    Returns:
        Nội dung chính của bài báo dưới dạng text, hoặc chuỗi rỗng nếu thất bại.
    """
    logger.info(f"Extracting content from URL: {url} using Trafilatura")
    # Tải và parse HTML
    downloaded = trafilatura.fetch_url(url)

    if downloaded is None:
        logger.warning(f"Failed to download content from {url}")
        return ""

    # Trích xuất nội dung chính
    # include_comments=False, include_tables=False để kết quả sạch hơn
    content = trafilatura.extract(
        downloaded,
        include_comments=False,
        include_tables=False,
        output_format='txt'
    )

    if not content:
        logger.warning(f"Trafilatura could not extract main content from {url}")
        return ""

    logger.info(f"Successfully extracted {len(content)} characters from {url}")
    return content 