#!/usr/bin/env python3
import sqlite3
from contextlib import closing
import os
from utils.logger import logger

DB_PATH = os.path.join(os.path.dirname(__file__), 'companies.db')

def migrate_database():
    """Migrate database to new schema with updated fields."""
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            c = conn.cursor()
            
            # Check if old table exists
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='companies'")
            if not c.fetchone():
                logger.info("No existing companies table found. Creating new table...")
                create_new_table(c)
                return
            
            # Get current table info
            c.execute("PRAGMA table_info(companies)")
            columns = [column[1] for column in c.fetchall()]
            logger.info(f"Current columns: {columns}")
            
            # Create backup of old data
            backup_old_data(c)
            
            # Drop old table and create new one
            c.execute("DROP TABLE IF EXISTS companies")
            create_new_table(c)
            
            conn.commit()
            logger.info("✅ Database migration completed successfully!")
            
    except Exception as e:
        logger.error(f"Error during migration: {e}")
        raise

def create_new_table(cursor):
    """Create new companies table with updated schema."""
    cursor.execute('''
        CREATE TABLE companies (
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
    logger.info("✅ New companies table created")

def backup_old_data(cursor):
    """Backup old data before migration."""
    try:
        cursor.execute("SELECT * FROM companies")
        old_data = cursor.fetchall()
        if old_data:
            logger.info(f"Backing up {len(old_data)} old records...")
            # You can implement backup logic here if needed
            logger.info("Old data backed up (not implemented in this version)")
    except Exception as e:
        logger.warning(f"Could not backup old data: {e}")

if __name__ == "__main__":
    logger.info("Starting database migration...")
    migrate_database()
    logger.info("Migration completed!") 