import logging
import os
from datetime import datetime

# Create logs directory if it doesn't exist
logs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
os.makedirs(logs_dir, exist_ok=True)

# Configure logging
log_filename = f"crawler_{datetime.now().strftime('%Y%m%d')}.log"
log_filepath = os.path.join(logs_dir, log_filename)

# Create logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create formatter
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Create file handler
file_handler = logging.FileHandler(log_filepath, encoding='utf-8')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)

# Create console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)

# Add handlers to logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Prevent duplicate logs
logger.propagate = False 