# Company Funding News Crawler

A web scraping application that automatically crawls TechCrunch and Finsmes to extract funding news and company information.

## Features

- **Automated Crawling**: Crawls TechCrunch and Finsmes for funding articles
- **LLM-Powered Extraction**: Uses OpenAI GPT to extract company information
- **Smart Deduplication**: Removes duplicate entries and normalizes data
- **Web Interface**: Streamlit-based UI to view and filter funding data
- **Google Search Integration**: Finds company websites and LinkedIn profiles

## Installation

1. **Clone the repository**

```bash
git clone <repository-url>
cd company_raisefund
```

2. **Install dependencies**

```bash
pip install -r requirements.txt
```

3. **Set up environment variables**
   Create a `.env` file in the project root:

```env
OPENAI_API_KEY=your_openai_api_key_here
```

## Usage

### 1. Run the crawler

```bash
# Crawl both TechCrunch and Finsmes
python crawl_all.py

# Or crawl specific source
python crawl_all.py techcrunch  # Only TechCrunch
python crawl_all.py finsmes     # Only Finsmes
```

### 2. Start the web interface

```bash
streamlit run app_streamlit.py
```

The web interface will be available at `http://localhost:8501`

## Project Structure

```
company_raisefund/
├── crawl_all.py           # Main crawling script
├── app_streamlit.py       # Web interface
├── techcrunch_crawler.py  # TechCrunch specific crawler
├── finsmes_crawler.py     # Finsmes specific crawler
├── llm_utils.py          # LLM integration utilities
├── search_utils.py       # Google search utilities
├── deduplication.py      # Data deduplication logic
├── extractors.py         # Article content extraction
├── config.py             # Configuration settings
├── companies.csv         # Output data file
└── requirements.txt      # Python dependencies
```

## Configuration

Edit `config.py` to customize:

- CSV file path
- Headers for web requests
- LLM model settings
- Crawling parameters

## Data Format

The application generates a CSV file with the following columns:

- `raised_date`: Date of funding announcement
- `company_name`: Company name
- `website`: Company website URL
- `linkedin`: Company LinkedIn URL
- `article_url`: Source article URL
- `source`: News source (TechCrunch/Finsmes)
- `crawl_date`: Date when data was crawled

## Dependencies

- **requests**: HTTP requests
- **beautifulsoup4**: HTML parsing
- **openai**: LLM API integration
- **pandas**: Data manipulation
- **streamlit**: Web interface
- **thefuzz**: Fuzzy string matching
- **googlesearch-python**: Google search integration
- **validators**: URL validation

## Production Deployment

For production deployment:

1. **Set up a virtual environment**

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. **Install production dependencies**

```bash
pip install -r requirements.txt
```

3. **Configure environment variables**

```bash
export OPENAI_API_KEY=your_api_key
```

4. **Run with process manager (e.g., PM2)**

```bash
pm2 start "streamlit run app_streamlit.py --server.port 8501"
```

## Troubleshooting

- **Import errors**: Ensure all dependencies are installed
- **API rate limits**: The crawler includes retry logic with exponential backoff
- **False positives**: The system includes logic to filter out non-funding articles

## License

This project is for internal company use only.
