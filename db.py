import sqlite3
from contextlib import closing
import os
from utils.logger import logger

DB_PATH = os.path.join(os.path.dirname(__file__), 'companies.db')

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    try:
        with closing(get_connection()) as conn:
            c = conn.cursor()
            c.execute('''
                CREATE TABLE IF NOT EXISTS companies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    raised_date TEXT,
                    company_name TEXT,
                    website TEXT,
                    linkedin TEXT,
                    article_url TEXT UNIQUE,
                    amount_raised TEXT,
                    funding_round TEXT,
                    crawl_date TEXT,
                    source TEXT
                )
            ''')
            conn.commit()
            logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise

def insert_company(data):
    try:
        with closing(get_connection()) as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO companies (
                    raised_date, company_name, website, linkedin, article_url, 
                    amount_raised, funding_round, crawl_date, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data.get('raised_date'),
                data.get('company_name'),
                data.get('website'),
                data.get('linkedin'),
                data.get('article_url'),
                data.get('amount_raised'),
                data.get('funding_round'),
                data.get('crawl_date'),
                data.get('source')
            ))
            conn.commit()
            logger.info(f"Successfully inserted: {data.get('company_name', 'N/A')}")
    except sqlite3.IntegrityError as e:
        logger.warning(f"Duplicate entry (article_url already exists): {data.get('article_url')}")
        logger.warning(f"Company: {data.get('company_name', 'N/A')}")
    except Exception as e:
        logger.error(f"Error inserting company: {e}")
        logger.error(f"Data: {data}")
        raise

def get_companies(start_date=None, end_date=None):
    try:
        with closing(get_connection()) as conn:
            c = conn.cursor()
            query = 'SELECT * FROM companies'
            params = []
            if start_date and end_date:
                query += ' WHERE date(raised_date) BETWEEN date(?) AND date(?)'
                params = [start_date, end_date]
            query += ' ORDER BY date(raised_date) DESC'
            c.execute(query, params)
            rows = c.fetchall()
            columns = [desc[0] for desc in c.description]
            return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        logger.error(f"Error getting companies: {e}")
        return []

def get_all_companies():
    """
    Get all article_urls from database for deduplication.
    """
    try:
        with closing(get_connection()) as conn:
            c = conn.cursor()
            c.execute('SELECT article_url FROM companies')
            rows = c.fetchall()
            return rows
    except Exception as e:
        logger.error(f"Error getting all companies: {e}")
        return []

def insert_many_companies(entries: list):
    """
    Insert multiple records into companies table at once.
    Uses 'INSERT OR IGNORE' to skip records with existing article_url.
    
    Args:
        entries: List of dicts containing company information
    
    Returns:
        Number of successfully inserted records
    """
    if not entries:
        return 0

    try:
        with closing(get_connection()) as conn:
            c = conn.cursor()
            # Convert list of dicts to list of tuples
            to_insert = [
                (
                    d.get('raised_date'),
                    d.get('company_name'),
                    d.get('website'),
                    d.get('linkedin'),
                    d.get('article_url'),
                    d.get('amount_raised'),
                    d.get('funding_round'),
                    d.get('crawl_date'),
                    d.get('source')
                ) for d in entries
            ]

            # 'OR IGNORE' will skip errors if article_url (UNIQUE) already exists
            c.executemany('''
                INSERT OR IGNORE INTO companies (
                    raised_date, company_name, website, linkedin, article_url, 
                    amount_raised, funding_round, crawl_date, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', to_insert)

            conn.commit()
            num_inserted = c.rowcount
            logger.info(f"Successfully inserted/ignored {len(entries)} entries. New rows: {num_inserted}")
            return num_inserted
    except Exception as e:
        logger.error(f"Error bulk inserting companies: {e}")
        logger.error(f"Data: {entries[:2]}...")  # Log first 2 entries for debugging
        raise 