import os
from datetime import date
import config
from deduplication import deduplicate_csv
from techcrunch_crawler import crawl_techcrunch, save_to_csv as save_techcrunch_csv
from finsmes_crawler import crawl_finsmes, save_to_csv as save_finsmes_csv

CSV_FILE = config.CSV_FILE

def crawl_all():
    """
    Crawl both TechCrunch and Finsmes, save results, and deduplicate.
    """
    today = date.today()
    all_entries = []
    
    print("=== Starting TechCrunch Crawler ===")
    tech_entries = crawl_techcrunch()
    if tech_entries:
        save_techcrunch_csv(tech_entries)
        print(f'Saved {len(tech_entries)} TechCrunch entries.')
        all_entries.extend(tech_entries)
    else:
        print('No new TechCrunch entries found.')
        # Add placeholder entry for TechCrunch
        with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
            from csv import writer
            w = writer(f)
            w.writerow([
                today.isoformat(),
                '---', '', '', '',
                'NO_NEWS_TECHCRUNCH',
                today.isoformat(),
                f'Không có tin mới TechCrunch ngày {today.isoformat()}'
            ])
    
    print("\n=== Starting Finsmes Crawler ===")
    finsmes_entries = crawl_finsmes()
    if finsmes_entries:
        save_finsmes_csv(finsmes_entries)
        print(f'Saved {len(finsmes_entries)} Finsmes entries.')
        all_entries.extend(finsmes_entries)
    else:
        print('No new Finsmes entries found.')
        # Add placeholder entry for Finsmes
        with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
            from csv import writer
            w = writer(f)
            w.writerow([
                today.isoformat(),
                '---', '', '', '',
                'NO_NEWS_FINSMES',
                today.isoformat(),
                f'Không có tin mới Finsmes ngày {today.isoformat()}'
            ])
    
    # Deduplicate CSV
    print("\n=== Deduplicating CSV ===")
    deduplicate_csv()
    
    print(f"\n=== Summary ===")
    print(f"Total entries processed: {len(all_entries)}")
    print(f"TechCrunch: {len([e for e in all_entries if e.get('source') == 'TechCrunch'])}")
    print(f"Finsmes: {len([e for e in all_entries if e.get('source') == 'Finsmes'])}")
    print("Done. Check companies.csv for results.")

def crawl_techcrunch_only():
    """
    Crawl only TechCrunch for testing.
    """
    print("=== TechCrunch Crawler Only ===")
    entries = crawl_techcrunch()
    if entries:
        save_techcrunch_csv(entries)
        print(f'Saved {len(entries)} TechCrunch entries.')
    else:
        print('No TechCrunch entries found.')
    print("Done. Check companies.csv for results.")

def crawl_finsmes_only():
    """
    Crawl only Finsmes for testing.
    """
    print("=== Finsmes Crawler Only ===")
    entries = crawl_finsmes()
    if entries:
        save_finsmes_csv(entries)
        print(f'Saved {len(entries)} Finsmes entries.')
    else:
        print('No Finsmes entries found.')
    print("Done. Check companies.csv for results.")

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
            print("Usage: python crawl_all.py [techcrunch|finsmes|all]")
            print("  techcrunch: Crawl only TechCrunch")
            print("  finsmes: Crawl only Finsmes") 
            print("  all: Crawl both (default)")
    else:
        crawl_all() 