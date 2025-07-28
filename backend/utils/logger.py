import logging
import os
from datetime import datetime

def setup_logger(name='company_crawler'):
    """
    Thiết lập logger tập trung cho toàn bộ project
    """
    # Tạo thư mục logs nếu chưa có
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # Tạo tên file log theo ngày
    log_file = os.path.join(log_dir, f'crawler_{datetime.now().strftime("%Y%m%d")}.log')
    
    # Cấu hình logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Tránh duplicate handlers
    if not logger.handlers:
        # Handler cho file
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        
        # Handler cho console
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    
    return logger

# Tạo logger instance mặc định
logger = setup_logger() 