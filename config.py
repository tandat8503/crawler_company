import os
from dotenv import load_dotenv

load_dotenv()

# API Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
LLM_API_URL = os.getenv('LLM_API_URL', 'https://vibe-agent-gateway.eternalai.org/v1/chat/completions')
LLM_MODEL_ID = os.getenv('LLM_MODEL_ID', 'gpt-4o-mini')

# Tavily API Configuration
TAVILY_API_KEY = os.getenv('TAVILY_API_KEY')

# HTTP Headers for web scraping
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}