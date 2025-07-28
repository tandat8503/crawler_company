import os
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any

from .. import config
from ..db import insert_company, insert_many_companies, init_db
from .techcrunch_crawler import crawl_techcrunch
from .finsmes_crawler import crawl_finsmes
from ..utils.logger import logger

# Dictionary để quản lý các crawler có sẵn
CRAWLERS = {
    'techcrunch': {
        'function': crawl_techcrunch,
        'name': 'TechCrunch',
        'description': 'Crawl TechCrunch for funding news'
    },
    'finsmes': {
        'function': crawl_finsmes,
        'name': 'Finsmes',
        'description': 'Crawl Finsmes for funding news'
    }
}

def run_single_crawler(crawler_name: str) -> List[Dict[str, Any]]:
    """
    Chạy một crawler cụ thể và trả về kết quả
    
    Args:
        crawler_name: Tên crawler (key trong CRAWLERS)
    
    Returns:
        List các entry từ crawler
    """
    if crawler_name not in CRAWLERS:
        logger.error(f"Crawler '{crawler_name}' không tồn tại")
        return []
    
    crawler_info = CRAWLERS[crawler_name]
    logger.info(f"=== Bắt đầu {crawler_info['name']} Crawler ===")
    
    try:
        entries = crawler_info['function']()
        if entries:
            logger.info(f"Đã tìm thấy {len(entries)} bản ghi từ {crawler_info['name']}")
            return entries
        else:
            logger.info(f'Không tìm thấy bản ghi {crawler_info["name"]} mới.')
            return []
    except Exception as e:
        logger.error(f"Lỗi khi crawl {crawler_info['name']}: {e}")
        logger.exception(f"Chi tiết lỗi {crawler_info['name']}:")
        return []

def run_crawlers(crawler_names: List[str] = None, parallel: bool = True) -> Dict[str, List[Dict[str, Any]]]:
    """
    Chạy một hoặc nhiều crawler
    
    Args:
        crawler_names: Danh sách tên crawler để chạy. Nếu None, chạy tất cả
        parallel: Có chạy song song hay không
    
    Returns:
        Dict với key là tên crawler, value là list entries
    """
    if crawler_names is None:
        crawler_names = list(CRAWLERS.keys())
    
    # Khởi tạo database
    try:
        init_db()
        logger.info("=== Khởi tạo database thành công ===")
    except Exception as e:
        logger.error(f"Lỗi khởi tạo database: {e}")
        return {}
    
    results = {}
    
    if parallel and len(crawler_names) > 1:
        # Chạy song song
        logger.info(f"Chạy {len(crawler_names)} crawler song song...")
        with ThreadPoolExecutor(max_workers=len(crawler_names)) as executor:
            future_to_crawler = {
                executor.submit(run_single_crawler, name): name 
                for name in crawler_names
            }
            
            for future in as_completed(future_to_crawler):
                crawler_name = future_to_crawler[future]
                try:
                    entries = future.result()
                    results[crawler_name] = entries
                except Exception as e:
                    logger.error(f"Lỗi khi chạy crawler {crawler_name}: {e}")
                    results[crawler_name] = []
    else:
        # Chạy tuần tự
        for crawler_name in crawler_names:
            entries = run_single_crawler(crawler_name)
            results[crawler_name] = entries
    
    return results

def save_entries_bulk(entries_by_crawler: Dict[str, List[Dict[str, Any]]]) -> Dict[str, int]:
    """
    Lưu tất cả entries vào database với bulk insert
    
    Args:
        entries_by_crawler: Dict với key là tên crawler, value là list entries
    
    Returns:
        Dict với key là tên crawler, value là số lượng entries đã lưu
    """
    save_results = {}
    
    for crawler_name, entries in entries_by_crawler.items():
        if not entries:
            save_results[crawler_name] = 0
            continue
            
        try:
            # Thêm source vào mỗi entry
            for entry in entries:
                entry['source'] = CRAWLERS[crawler_name]['name']
            
            # Bulk insert
            saved_count = insert_many_companies(entries)
            save_results[crawler_name] = saved_count
            
            logger.info(f"Đã lưu {saved_count}/{len(entries)} bản ghi từ {CRAWLERS[crawler_name]['name']}")
            
        except Exception as e:
            logger.error(f"Lỗi khi lưu entries từ {crawler_name}: {e}")
            save_results[crawler_name] = 0
    
    return save_results

def crawl_all():
    """
    Crawl cả TechCrunch và Finsmes, lưu kết quả và xử lý lỗi gracefully
    """
    logger.info("=== Bắt đầu crawl tất cả nguồn ===")
    
    # Chạy tất cả crawler
    results = run_crawlers()
    
    # Lưu kết quả
    save_results = save_entries_bulk(results)
    
    # Tóm tắt kết quả
    logger.info(f"\n=== TÓM TẮT ===")
    total_entries = sum(len(entries) for entries in results.values())
    total_saved = sum(save_results.values())
    logger.info(f"Tổng số bản ghi đã xử lý: {total_entries}")
    logger.info(f"Tổng số bản ghi đã lưu: {total_saved}")
    
    for crawler_name, entries in results.items():
        saved_count = save_results[crawler_name]
        logger.info(f"{CRAWLERS[crawler_name]['name']}: {len(entries)} entries, {saved_count} saved")
    
    logger.info("Hoàn tất. Kiểm tra cơ sở dữ liệu để xem kết quả.")

def crawl_techcrunch_only():
    """Chỉ crawl TechCrunch để test"""
    logger.info("=== Chỉ TechCrunch Crawler ===")
    results = run_crawlers(['techcrunch'], parallel=False)
    save_results = save_entries_bulk(results)
    
    entries = results.get('techcrunch', [])
    saved_count = save_results.get('techcrunch', 0)
    logger.info(f"Đã lưu {saved_count}/{len(entries)} bản ghi TechCrunch.")
    logger.info("Hoàn tất. Kiểm tra cơ sở dữ liệu để xem kết quả.")

def crawl_finsmes_only():
    """Chỉ crawl Finsmes để test"""
    logger.info("=== Chỉ Finsmes Crawler ===")
    results = run_crawlers(['finsmes'], parallel=False)
    save_results = save_entries_bulk(results)
    
    entries = results.get('finsmes', [])
    saved_count = save_results.get('finsmes', 0)
    logger.info(f"Đã lưu {saved_count}/{len(entries)} bản ghi Finsmes.")
    logger.info("Hoàn tất. Kiểm tra cơ sở dữ liệu để xem kết quả.")

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        if sys.argv[1] == 'techcrunch':
            crawl_techcrunch_only()
        elif sys.argv[1] == 'finsmes':
            crawl_finsmes_only()
        elif sys.argv[1] == 'all':
            crawl_all()
        else:
            logger.info("Cách sử dụng: python crawl_all.py [techcrunch|finsmes|all]")
            logger.info("  techcrunch: Chỉ crawl TechCrunch")
            logger.info("  finsmes: Chỉ crawl Finsmes") 
            logger.info("  all: Crawl cả hai (mặc định)")
    else:
        crawl_all() 