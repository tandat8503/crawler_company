import sqlite3
import os
from contextlib import closing
from utils.logger import logger

DB_PATH = os.path.join(os.path.dirname(__file__), 'companies.db')

def init_db():
    """Initialize the database with the new schema."""
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            c = conn.cursor()
            c.execute('''
                CREATE TABLE IF NOT EXISTS companies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    raised_date TEXT,
                    company_name TEXT,
                    industry TEXT,
                    ceo_name TEXT,
                    procurement_name TEXT,
                    purchasing_name TEXT,
                    manager_name TEXT,
                    amount_raised TEXT,
                    funding_round TEXT,
                    source TEXT,
                    website TEXT,
                    linkedin TEXT,
                    article_url TEXT UNIQUE
                )
            ''')
            conn.commit()
            logger.info("✅ Database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise

def insert_company(raised_date, company_name, industry, ceo_name, procurement_name, 
                  purchasing_name, manager_name, amount_raised, funding_round, 
                  source, website, linkedin, article_url):
    """Insert a single company record."""
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            c = conn.cursor()
            c.execute('''
                INSERT OR IGNORE INTO companies (
                    raised_date, company_name, industry, ceo_name, procurement_name,
                    purchasing_name, manager_name, amount_raised, funding_round,
                    source, website, linkedin, article_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (raised_date, company_name, industry, ceo_name, procurement_name,
                  purchasing_name, manager_name, amount_raised, funding_round,
                  source, website, linkedin, article_url))
            conn.commit()
            return c.rowcount
    except Exception as e:
        logger.error(f"Error inserting company: {e}")
        return 0

def insert_many_companies(entries):
    """Insert multiple company records."""
    if not entries:
        return 0

    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            c = conn.cursor()
            to_insert = [
                (
                    d.get('raised_date'),
                    d.get('company_name'),
                    d.get('industry'),
                    d.get('ceo_name'),
                    d.get('procurement_name'),
                    d.get('purchasing_name'),
                    d.get('manager_name'),
                    d.get('amount_raised'),
                    d.get('funding_round'),
                    d.get('source'),
                    d.get('website'),
                    d.get('linkedin'),
                    d.get('article_url')
                ) for d in entries
            ]
            c.executemany('''
                INSERT OR IGNORE INTO companies (
                    raised_date, company_name, industry, ceo_name, procurement_name,
                    purchasing_name, manager_name, amount_raised, funding_round,
                    source, website, linkedin, article_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', to_insert)
            conn.commit()
            return c.rowcount
    except Exception as e:
        logger.error(f"Error inserting many companies: {e}")
        return 0

def get_all_companies():
    """Get all companies from database."""
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            c = conn.cursor()
            c.execute('''
                SELECT raised_date, company_name, industry, ceo_name, procurement_name,
                       purchasing_name, manager_name, amount_raised, funding_round,
                       source, website, linkedin, article_url
                FROM companies 
                ORDER BY id DESC
            ''')
            return c.fetchall()
    except Exception as e:
        logger.error(f"Error getting companies: {e}")
        return []

def get_company_count():
    """Get total number of companies."""
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM companies')
            return c.fetchone()[0]
    except Exception as e:
        logger.error(f"Error getting company count: {e}")
        return 0

def search_companies(query):
    """Search companies by name or description."""
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            c = conn.cursor()
            c.execute('''
                SELECT raised_date, company_name, industry, ceo_name, procurement_name,
                       purchasing_name, manager_name, amount_raised, funding_round,
                       source, website, linkedin, article_url
                FROM companies 
                WHERE company_name LIKE ? OR industry LIKE ? OR ceo_name LIKE ?
                ORDER BY id DESC
            ''', (f'%{query}%', f'%{query}%', f'%{query}%'))
            return c.fetchall()
    except Exception as e:
        logger.error(f"Error searching companies: {e}")
        return []

def get_companies_by_source(source):
    """Get companies by source."""
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            c = conn.cursor()
            c.execute('''
                SELECT raised_date, company_name, industry, ceo_name, procurement_name,
                       purchasing_name, manager_name, amount_raised, funding_round,
                       source, website, linkedin, article_url
                FROM companies 
                WHERE source = ?
                ORDER BY id DESC
            ''', (source,))
            return c.fetchall()
    except Exception as e:
        logger.error(f"Error getting companies by source: {e}")
        return []

def get_companies_by_date_range(start_date, end_date):
    """Get companies within a date range."""
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            c = conn.cursor()
            c.execute('''
                SELECT raised_date, company_name, industry, ceo_name, procurement_name,
                       purchasing_name, manager_name, amount_raised, funding_round,
                       source, website, linkedin, article_url
                FROM companies 
                WHERE raised_date BETWEEN ? AND ?
                ORDER BY raised_date DESC
            ''', (start_date, end_date))
            return c.fetchall()
    except Exception as e:
        logger.error(f"Error getting companies by date range: {e}")
        return []

def get_latest_companies(limit=10):
    """Get latest companies."""
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            c = conn.cursor()
            c.execute('''
                SELECT raised_date, company_name, industry, ceo_name, procurement_name,
                       purchasing_name, manager_name, amount_raised, funding_round,
                       source, website, linkedin, article_url
                FROM companies 
                ORDER BY id DESC
                LIMIT ?
            ''', (limit,))
            return c.fetchall()
    except Exception as e:
        logger.error(f"Error getting latest companies: {e}")
        return []

def delete_company_by_url(article_url):
    """Delete a company by article URL."""
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            c = conn.cursor()
            c.execute('DELETE FROM companies WHERE article_url = ?', (article_url,))
            conn.commit()
            return c.rowcount
    except Exception as e:
        logger.error(f"Error deleting company: {e}")
        return 0

def clear_all_companies():
    """Clear all companies from database."""
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            c = conn.cursor()
            c.execute('DELETE FROM companies')
            conn.commit()
            logger.info("✅ All companies cleared from database")
            return True
    except Exception as e:
        logger.error(f"Error clearing companies: {e}")
        return False

# Initialize database when module is imported
init_db() 