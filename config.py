from dotenv import load_dotenv
import os
load_dotenv()

LLM_API_URL = os.getenv("LLM_API_URL", "https://api.openai.com/v1/chat/completions")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL_ID = os.getenv("LLM_MODEL_ID", "gpt-4o-mini")

if not LLM_API_URL:
    raise ValueError("Chưa thiết lập LLM_API_URL trong .env")

if not OPENAI_API_KEY:
    raise ValueError("Chưa thiết lập OPENAI_API_KEY trong .env")

CSV_FILE = os.path.join(os.path.dirname(__file__), 'companies.csv')
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; CompanyFundBot/1.0)'
}