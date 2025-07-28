from dotenv import load_dotenv
import os

# Load .env file from the backend directory
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)

LLM_API_URL = os.getenv("LLM_API_URL", "https://vibe-agent-gateway.eternalai.org/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL_ID = os.getenv("LLM_MODEL_ID", "gpt-4o-mini")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")


CSV_FILE = os.path.join(os.path.dirname(__file__), '../companies.csv')
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; CompanyFundBot/1.0)'
}