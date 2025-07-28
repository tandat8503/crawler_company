#!/usr/bin/env python3
"""
Script để migrate database cũ sang schema mới
"""

import sqlite3
import os
from backend.utils.logger import logger

DB_PATH = os.path.join(os.path.dirname(__file__), 'companies.db')

def migrate_database():
    """Migrate database từ schema cũ sang schema mới"""
    
    if not os.path.exists(DB_PATH):
        logger.info("Database không tồn tại, sẽ được tạo mới với schema đúng.")
        return
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Kiểm tra xem cột source đã tồn tại chưa
        cursor.execute("PRAGMA table_info(companies)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'source' not in columns:
            logger.info("Thêm cột 'source' vào bảng companies...")
            cursor.execute("ALTER TABLE companies ADD COLUMN source TEXT")
            conn.commit()
            logger.info("✅ Đã thêm cột 'source' thành công")
        else:
            logger.info("✅ Cột 'source' đã tồn tại")
        
        # Kiểm tra và thêm các cột khác nếu cần
        required_columns = ['id', 'raised_date', 'company_name', 'website', 'linkedin', 
                          'article_url', 'amount_raised', 'funding_round', 'crawl_date', 'source']
        
        missing_columns = []
        for col in required_columns:
            if col not in columns:
                missing_columns.append(col)
        
        if missing_columns:
            logger.warning(f"Các cột bị thiếu: {missing_columns}")
            logger.warning("Có thể cần tạo lại database")
        
        conn.close()
        logger.info("✅ Migration hoàn tất")
        
    except Exception as e:
        logger.error(f"❌ Lỗi migration: {e}")
        raise

def recreate_database():
    """Tạo lại database với schema đúng"""
    
    try:
        # Xóa database cũ
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
            logger.info("Đã xóa database cũ")
        
        # Import và chạy init_db
        from backend.db import init_db
        init_db()
        logger.info("✅ Đã tạo database mới với schema đúng")
        
    except Exception as e:
        logger.error(f"❌ Lỗi tạo lại database: {e}")
        raise

if __name__ == "__main__":
    logger.info("=== Database Migration ===")
    
    choice = input("Chọn phương án:\n1. Migrate database hiện tại\n2. Tạo lại database mới\nNhập lựa chọn (1 hoặc 2): ")
    
    if choice == "1":
        migrate_database()
    elif choice == "2":
        recreate_database()
    else:
        logger.error("Lựa chọn không hợp lệ") 