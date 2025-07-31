import streamlit as st
import asyncio
import pandas as pd
from datetime import datetime, timedelta
import sqlite3
import os
from universal_crawler import crawl_url_async, crawl_urls_async, crawl_list_page_async, get_supported_sources, universal_crawler
from db import get_all_companies, get_company_count, search_companies, get_companies_by_source, get_companies_by_date_range, get_latest_companies, clear_all_companies
from utils.logger import logger
from typing import List, Dict, Any

# Page config
st.set_page_config(
    page_title="Company Funding Crawler",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
    }
    .success-message {
        background-color: #d4edda;
        color: #155724;
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid #c3e6cb;
    }
    .error-message {
        background-color: #f8d7da;
        color: #721c24;
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid #f5c6cb;
    }
    </style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=300)  # Cache data for 5 minutes instead of 1 hour
def get_database_stats():
    """Get database statistics with caching."""
    try:
        total_companies = get_company_count()
        latest_companies = get_latest_companies(5)
        return total_companies, latest_companies
    except Exception as e:
        logger.error(f"Error getting database stats: {e}")
        return 0, []

@st.cache_data(ttl=300)  # Cache data for 5 minutes instead of 30 minutes
def fetch_all_companies():
    """Fetch all companies from database with caching."""
    try:
        return get_all_companies()
    except Exception as e:
        logger.error(f"Error fetching companies: {e}")
        return []

def display_company_data(companies_data, show_save_button=True, save_to_db=False):
    """Display company data in a formatted table with optional save button."""
    if not companies_data:
        st.warning("No data to display")
        return
    
    # Convert to DataFrame for better display
    columns = [
        'raised_date', 'company_name', 'industry', 'ceo_name', 'procurement_name',
        'purchasing_name', 'manager_name', 'amount_raised', 'funding_round',
        'source', 'website', 'linkedin', 'article_url'
    ]
    
    df = pd.DataFrame(companies_data, columns=columns)
    
    # Display save button if requested
    if show_save_button and not save_to_db:
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            st.success(f"📊 **{len(companies_data)} records ready for review**")
        with col2:
            if st.button("💾 Save to Database", type="primary", key=f"save_btn_{len(companies_data)}"):
                try:
                    from db import insert_many_companies
                    num_inserted = insert_many_companies(companies_data)
                    st.success(f"✅ Successfully saved {num_inserted} records to database!")
                    
                    # Auto-refresh cache
                    st.info("🔄 Refreshing data...")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error saving to database: {str(e)}")
        with col3:
            if st.button("🔄 Refresh", key=f"refresh_btn_{len(companies_data)}"):
                st.cache_data.clear()
                st.rerun()
    else:
        st.success(f"📊 **{len(companies_data)} records**")
    
    # Format the display
    st.dataframe(
        df,
        use_container_width=True,
        column_config={
            "raised_date": st.column_config.DateColumn("Published Date"),
            "company_name": st.column_config.TextColumn("Company Name", width="medium"),
            "industry": st.column_config.TextColumn("Industry", width="medium"),
            "ceo_name": st.column_config.TextColumn("CEO Name", width="medium"),
            "procurement_name": st.column_config.TextColumn("Procurement", width="medium"),
            "purchasing_name": st.column_config.TextColumn("Purchasing", width="medium"),
            "manager_name": st.column_config.TextColumn("Manager", width="medium"),
            "amount_raised": st.column_config.NumberColumn("Amount Raised", format="$%d"),
            "funding_round": st.column_config.TextColumn("Funding Round", width="medium"),
            "source": st.column_config.TextColumn("Source", width="small"),
            "website": st.column_config.LinkColumn("Website"),
            "linkedin": st.column_config.LinkColumn("LinkedIn"),
            "article_url": st.column_config.LinkColumn("Article URL")
        }
    )

def main():
    st.markdown('<h1 class="main-header">💰 Company Funding Crawler</h1>', unsafe_allow_html=True)
    
    # Sidebar navigation
    st.sidebar.title("Navigation")
    page = st.sidebar.selectbox(
        "Choose a page:",
        ["🏠 Home", "🤖 Natural Language Crawler", "🚀 AI Auto-Discovery", "🕷️ Universal Crawler", "📊 Data View", "🔍 Search & Filter", "⚙️ Settings"]
    )
    
    if page == "🏠 Home":
        show_dashboard()
    elif page == "🤖 Natural Language Crawler":
        show_natural_language_crawler()
    elif page == "🚀 AI Auto-Discovery":
        show_ai_auto_discovery()
    elif page == "🕷️ Universal Crawler":
        show_universal_crawler()
    elif page == "📊 Data View":
        show_data_view()
    elif page == "🔍 Search & Filter":
        show_search_filter()
    elif page == "⚙️ Settings":
        show_settings()

def show_dashboard():
    """Display the main dashboard."""
    st.header("📊 Home")
    
    # Add refresh button
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown("### Dashboard")
    with col2:
        if st.button("🔄 Refresh Data", help="Clear cache and refresh data"):
            st.cache_data.clear()
            st.rerun()
    
    # Get database statistics
    total_companies, latest_companies = get_database_stats()
    
    # Display metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Companies", total_companies)
    
    with col2:
        st.metric("Latest Update", datetime.now().strftime("%Y-%m-%d"))
    
    with col3:
        sources = get_supported_sources()
        st.metric("Supported Sources", len(sources))
    
    with col4:
        if latest_companies:
            latest_date = latest_companies[0][0] if latest_companies[0][0] else "N/A"
            st.metric("Latest Article", latest_date)
    
    # Display latest companies
    st.subheader("📈 Latest Companies")
    if latest_companies:
        display_company_data(latest_companies)
    else:
        st.info("No companies in database yet. Start crawling to see data here!")

def show_universal_crawler():
    """Display the universal crawler interface."""
    st.header("🕷️ Universal Crawler")
    
    # Supported sources info with detailed breakdown
    sources = get_supported_sources()
    st.info(f"✅ **{len(sources)} Supported Sources**")
    
    # Show sources in a more organized way
    col1, col2, col3 = st.columns(3)
    source_list = list(sources.values())

    with col1:
        st.markdown("**Major Tech News:**")
        for source in source_list[:7]:
            st.write(f"• {source}")

    with col2:
        st.markdown("**Business & Finance:**")
        for source in source_list[7:14]:
            st.write(f"• {source}")

    with col3:
        st.markdown("**Startup & VC:**")
        for source in source_list[14:]:
            st.write(f"• {source}")

    st.info("🌐 **Auto-Detection**: The system can also automatically detect and process other news sources based on domain patterns!")
    
    # List Page crawling
    st.markdown("### 📰 List Page Crawling")
    list_page_url = st.text_input("List Page URL:", placeholder="https://techcrunch.com/startups/")
    
    # Date range filtering
    st.markdown("#### 📅 Date Range Filter (Optional)")
    col1, col2 = st.columns(2)
    
    with col1:
        start_date = st.date_input("Start Date:", value=None)
    with col2:
        end_date = st.date_input("End Date:", value=None)
    
    # Save to database option
    save_to_db = st.checkbox("💾 Auto Save to Database", value=False, help="Nếu bỏ chọn, bạn sẽ có thể xem xét dữ liệu trước khi lưu")
    
    if st.button("🚀 Crawl List Page", type="primary"):
        if list_page_url:
            # Validate date range
            if (start_date and not end_date) or (end_date and not start_date):
                st.error("❌ Please select both start and end dates for date filtering")
            elif start_date and end_date and start_date > end_date:
                st.error("❌ Start date cannot be after end date")
            else:
                with st.spinner("Crawling list page..."):
                    try:
                        # Use default values: max_articles=20, num_workers=5
                        results = asyncio.run(crawl_list_page_async(
                            list_page_url, 20, 5, save_to_db,
                            start_date.strftime('%Y-%m-%d') if start_date else None,
                            end_date.strftime('%Y-%m-%d') if end_date else None
                        ))

                        if results:
                            st.success(f"✅ Successfully processed {len(results)} articles!")
                            
                            # Display results summary
                            successful = [r for r in results if r.get('success')]
                            st.info(f"📊 Summary: {len(successful)} successful out of {len(results)} total")
                            
                            # Display results in table format
                            if successful:
                                # Convert to table format
                                table_data = []
                                for result in successful:
                                    table_data.append({
                                        'raised_date': result.get('raised_date'),
                                        'company_name': result.get('company_name'),
                                        'industry': result.get('industry'),
                                        'ceo_name': result.get('ceo_name'),
                                        'procurement_name': result.get('procurement_name'),
                                        'purchasing_name': result.get('purchasing_name'),
                                        'manager_name': result.get('manager_name'),
                                        'amount_raised': result.get('amount_raised'),
                                        'funding_round': result.get('funding_round'),
                                        'source': result.get('source'),
                                        'website': result.get('website'),
                                        'linkedin': result.get('linkedin'),
                                        'article_url': result.get('article_url')
                                    })
                                
                                st.success(f"📊 Displaying {len(table_data)} successful results:")
                                display_company_data(table_data, show_save_button=not save_to_db, save_to_db=save_to_db)
                            
                            # Show failed results in expander
                            failed_results = [r for r in results if not r.get('success')]
                            if failed_results:
                                with st.expander(f"⚠️ {len(failed_results)} Failed Results"):
                                    for i, result in enumerate(failed_results):
                                        st.error(f"**{i+1}. {result.get('url', 'Unknown URL')}**: {result.get('error')}")
                            
                            # Auto-refresh cache after successful crawl
                            if save_to_db and successful:
                                st.info("🔄 Refreshing data...")
                                st.cache_data.clear()
                                st.rerun()
                        else:
                            st.warning("⚠️ No articles found or processed")
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
        else:
            st.warning("Please enter a list page URL")

def show_data_view():
    """Display the data view page."""
    st.header("📊 Data View")
    
    # Get all companies
    companies_data = fetch_all_companies()
    
    if companies_data:
        st.success(f"📈 Found {len(companies_data)} companies in database")
        display_company_data(companies_data, show_save_button=False, save_to_db=True)
        
        # Export options
        st.markdown("### 📤 Export Data")
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📊 Export to CSV"):
                df = pd.DataFrame(companies_data, columns=[
                    'raised_date', 'company_name', 'industry', 'ceo_name', 'procurement_name',
                    'purchasing_name', 'manager_name', 'amount_raised', 'funding_round',
                    'source', 'website', 'linkedin', 'article_url'
                ])
                csv = df.to_csv(index=False)
                st.download_button(
                    label="Download CSV",
                    data=csv,
                    file_name=f"companies_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
        
        with col2:
            if st.button("🗑️ Clear All Data"):
                if st.button("⚠️ Confirm Clear All Data", type="secondary"):
                    if clear_all_companies():
                        st.success("✅ All data cleared successfully!")
                        st.rerun()
            else:
                        st.error("❌ Failed to clear data")
    else:
        st.info("📭 No data in database. Start crawling to see data here!")

def show_search_filter():
    """Display the search and filter page."""
    st.header("🔍 Search & Filter")
    
    # Search functionality
    st.markdown("### 🔍 Search Companies")
    search_query = st.text_input("Search by company name, industry, or CEO name:")
    
    if search_query:
        search_results = search_companies(search_query)
        if search_results:
            st.success(f"🔍 Found {len(search_results)} matching companies")
            display_company_data(search_results, show_save_button=False, save_to_db=True)
        else:
            st.info("🔍 No companies found matching your search")
    
    # Filter by source
    st.markdown("### 📰 Filter by Source")
    sources = get_supported_sources()
    selected_source = st.selectbox("Select source:", ["All"] + list(sources.values()))
    
    if selected_source != "All":
        source_results = get_companies_by_source(selected_source)
        if source_results:
            st.success(f"📰 Found {len(source_results)} companies from {selected_source}")
            display_company_data(source_results, show_save_button=False, save_to_db=True)
    else:
            st.info(f"📰 No companies found from {selected_source}")
    
    # Filter by date range
    st.markdown("### 📅 Filter by Date Range")
    col1, col2 = st.columns(2)
    
    with col1:
        filter_start_date = st.date_input("Start Date:", value=None)
    with col2:
        filter_end_date = st.date_input("End Date:", value=None)
    
    if filter_start_date and filter_end_date:
        if filter_start_date <= filter_end_date:
            date_results = get_companies_by_date_range(
                filter_start_date.strftime('%Y-%m-%d'),
                filter_end_date.strftime('%Y-%m-%d')
            )
            if date_results:
                st.success(f"📅 Found {len(date_results)} companies in date range")
                display_company_data(date_results, show_save_button=False, save_to_db=True)
            else:
                st.info("📅 No companies found in selected date range")
        else:
            st.error("❌ Start date must be before or equal to end date")

def show_settings():
    """Display the settings page."""
    st.header("⚙️ Settings")
    
    # Database information
    st.markdown("### 💾 Database Information")
    total_companies = get_company_count()
    st.info(f"📊 Total companies in database: {total_companies}")
    
    # Supported sources
    st.markdown("### 🌐 Supported Sources")
    sources = get_supported_sources()
    for source, name in sources.items():
        st.write(f"✅ {name}")
    
    # System information
    st.markdown("### 🖥️ System Information")
    st.write(f"🕒 Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    st.write(f"📁 Working directory: {os.getcwd()}")
    
    # Clear data option
    st.markdown("### 🗑️ Data Management")
    if st.button("🗑️ Clear All Data", type="secondary"):
        st.warning("⚠️ This will permanently delete all data!")
        if st.button("⚠️ Confirm Delete All Data", type="secondary"):
            if clear_all_companies():
                st.success("✅ All data cleared successfully!")
                st.rerun()
            else:
                st.error("❌ Failed to clear data")

def show_natural_language_crawler():
    """Display the natural language crawler interface."""
    st.header("🤖 Natural Language Crawler")
    
    st.info("💡 **Cách sử dụng**: Nhập yêu cầu bằng tiếng Việt hoặc tiếng Anh, hệ thống sẽ tự động hiểu và crawl dữ liệu!")
    
    # Example prompts
    with st.expander("📝 Ví dụ các prompt có thể sử dụng"):
        st.markdown("""
        **Tiếng Việt:**
        - "Tôi muốn lấy tin từ vnexpress"
        - "Crawl dữ liệu từ trang techcrunch.com/startups"
        - "Lấy tin tức funding từ finsmes.com"
        - "Tìm bài báo về startup funding trên crunchbase"
        
        **English:**
        - "I want to crawl news from vnexpress"
        - "Get funding articles from techcrunch startups section"
        - "Extract data from finsmes.com"
        - "Find startup funding news on crunchbase"
        """)
    
    # Natural language input
    user_prompt = st.text_area(
        "Nhập yêu cầu của bạn:",
        placeholder="Ví dụ: Tôi muốn lấy tin từ vnexpress hoặc Crawl dữ liệu từ techcrunch.com/startups",
        height=100
    )
    
    # Advanced options
    with st.expander("⚙️ Tùy chọn nâng cao"):
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Từ ngày:", value=None)
        with col2:
            end_date = st.date_input("Đến ngày:", value=None)
        
        save_to_db = st.checkbox("💾 Tự động lưu vào Database", value=False, help="Nếu bỏ chọn, bạn sẽ có thể xem xét dữ liệu trước khi lưu")
        max_articles = st.slider("Số bài báo tối đa:", min_value=5, max_value=50, value=20)
    
    if st.button("🚀 Crawl theo yêu cầu", type="primary"):
        if user_prompt:
            with st.spinner("Đang phân tích yêu cầu và crawl dữ liệu..."):
                try:
                    # Parse natural language prompt
                    parsed_url = parse_natural_language_prompt(user_prompt)
                    
                    if parsed_url:
                        st.success(f"✅ Đã hiểu yêu cầu: {parsed_url}")
                        
                        # Crawl the parsed URL
                        results = asyncio.run(crawl_list_page_async(
                            parsed_url, max_articles, 5, save_to_db,
                            start_date.strftime('%Y-%m-%d') if start_date else None,
                            end_date.strftime('%Y-%m-%d') if end_date else None
                        ))
                        
                        if results:
                            st.success(f"✅ Đã xử lý thành công {len(results)} bài báo!")
                            
                            # Display results summary
                            successful = [r for r in results if r.get('success')]
                            st.info(f"📊 Kết quả: {len(successful)} thành công / {len(results)} tổng cộng")
                            
                            # Display results in table format
                            if successful:
                                table_data = []
                                for result in successful:
                                    table_data.append({
                                        'raised_date': result.get('raised_date'),
                                        'company_name': result.get('company_name'),
                                        'industry': result.get('industry'),
                                        'ceo_name': result.get('ceo_name'),
                                        'procurement_name': result.get('procurement_name'),
                                        'purchasing_name': result.get('purchasing_name'),
                                        'manager_name': result.get('manager_name'),
                                        'amount_raised': result.get('amount_raised'),
                                        'funding_round': result.get('funding_round'),
                                        'source': result.get('source'),
                                        'website': result.get('website'),
                                        'linkedin': result.get('linkedin'),
                                        'article_url': result.get('article_url')
                                    })
                                
                                st.success(f"📊 Hiển thị {len(table_data)} kết quả thành công:")
                                display_company_data(table_data, show_save_button=not save_to_db, save_to_db=save_to_db)
                            
                            # Show failed results
                            failed_results = [r for r in results if not r.get('success')]
                            if failed_results:
                                with st.expander(f"⚠️ {len(failed_results)} kết quả thất bại"):
                                    for i, result in enumerate(failed_results):
                                        st.error(f"**{i+1}. {result.get('url', 'URL không xác định')}**: {result.get('error')}")
                            
                            # Auto-refresh cache
                            if save_to_db and successful:
                                st.info("🔄 Đang cập nhật dữ liệu...")
                                st.cache_data.clear()
                                st.rerun()
                        else:
                            st.warning("⚠️ Không tìm thấy bài báo nào")
                    else:
                        st.error("❌ Không thể hiểu yêu cầu. Vui lòng thử lại với prompt rõ ràng hơn.")
                        
                except Exception as e:
                    st.error(f"❌ Lỗi: {str(e)}")
        else:
            st.warning("Vui lòng nhập yêu cầu của bạn")

def parse_natural_language_prompt(prompt):
    """Parse natural language prompt to extract URL and parameters."""
    prompt_lower = prompt.lower()
    
    # Common Vietnamese patterns
    vietnamese_patterns = [
        r'từ\s+(https?://[^\s]+)',
        r'từ\s+([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
        r'vnexpress',
        r'techcrunch',
        r'finsmes',
        r'crunchbase',
        r'startup',
        r'funding',
        r'raise fund',
        r'gọi vốn',
        r'tin tức',
        r'báo',
        r'trang web',
        r'website'
    ]
    
    # Common English patterns
    english_patterns = [
        r'from\s+(https?://[^\s]+)',
        r'from\s+([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
        r'vnexpress',
        r'techcrunch',
        r'finsmes',
        r'crunchbase',
        r'startup',
        r'funding',
        r'news',
        r'website'
    ]
    
    # Check for direct URLs
    import re
    url_match = re.search(r'https?://[^\s]+', prompt)
    if url_match:
        return url_match.group(0)
    
    # Check for domain names
    domain_match = re.search(r'([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', prompt)
    if domain_match:
        domain = domain_match.group(1)
        # Add protocol if missing
        if not domain.startswith(('http://', 'https://')):
            return f"https://{domain}"
    
    # Map common keywords to URLs with better Vietnamese support
    keyword_mapping = {
        'vnexpress': 'https://vnexpress.net',
        'techcrunch': 'https://techcrunch.com/startups/',
        'finsmes': 'https://finsmes.com/',
        'crunchbase': 'https://news.crunchbase.com/sections/fintech-ecommerce/',
        'startup': 'https://techcrunch.com/startups/',
        'funding': 'https://finsmes.com/',
        'raise fund': 'https://finsmes.com/',
        'gọi vốn': 'https://finsmes.com/',
        'tin tức': 'https://vnexpress.net',
        'báo': 'https://vnexpress.net',
        'trang web': None,  # Will be handled by domain detection
        'website': None,    # Will be handled by domain detection
        'news': 'https://techcrunch.com/startups/'
    }
    
    # Check for Vietnamese funding-related keywords
    funding_keywords = ['raise fund', 'gọi vốn', 'funding', 'startup']
    for keyword in funding_keywords:
        if keyword in prompt_lower:
            # Prefer funding-specific sources
            if 'vnexpress' in prompt_lower:
                return 'https://vnexpress.net'
            elif 'techcrunch' in prompt_lower:
                return 'https://techcrunch.com/startups/'
            else:
                return 'https://finsmes.com/'
    
    # Check for general news keywords
    news_keywords = ['tin tức', 'báo', 'news']
    for keyword in news_keywords:
        if keyword in prompt_lower:
            if 'vnexpress' in prompt_lower:
                return 'https://vnexpress.net'
            elif 'techcrunch' in prompt_lower:
                return 'https://techcrunch.com/startups/'
            else:
                return 'https://vnexpress.net'
    
    # Check for specific website names
    for keyword, url in keyword_mapping.items():
        if keyword in prompt_lower and url:
            return url
    
    # If no specific match, try to extract any domain-like pattern
    domain_pattern = re.search(r'([a-zA-Z0-9-]+\.(com|net|org|vn|co|io))', prompt)
    if domain_pattern:
        domain = domain_pattern.group(1)
        return f"https://{domain}"
    
    return None

def show_ai_auto_discovery():
    """Display the AI Auto-Discovery interface."""
    st.header("🤖 AI Auto-Discovery")
    
    st.info("🚀 **Tính năng mới**: AI sẽ tự động phân tích và crawl bất kỳ trang web nào mà không cần cấu hình trước!")
    
    # Features explanation
    with st.expander("✨ Tính năng AI Auto-Discovery"):
        st.markdown("""
        **🤖 AI phân tích website:**
        - Tự động hiểu cấu trúc website
        - Xác định loại website (news, blog, e-commerce...)
        - Tìm chiến lược crawl tối ưu
        
        **🔍 Tự động phát hiện:**
        - Tìm navigation links
        - Phát hiện article patterns
        - Xác định content selectors
        
        **📰 Crawl thông minh:**
        - Sử dụng sitemap nếu có
        - Crawl category pages
        - Fallback về generic strategy
        
        **🎯 Không cần cấu hình:**
        - Không cần thêm vào sources.json
        - Không cần viết code mới
        - Hoạt động với mọi website
        """)
    
    # Input section with smart detection
    st.markdown("### 🌐 Nhập thông tin website")
    
    # Input method selection
    input_method = st.radio(
        "Chọn cách nhập:",
        ["🔗 URL trực tiếp", "🤖 Prompt tự nhiên"],
        horizontal=True
    )
    
    if input_method == "🔗 URL trực tiếp":
        website_input = st.text_input(
            "Nhập URL website:",
            placeholder="https://example.com hoặc https://news.example.com",
            help="Nhập URL bất kỳ website nào bạn muốn crawl"
        )
        
        # Validate URL
        if website_input:
            if not is_valid_url(website_input):
                st.error("❌ URL không hợp lệ. Vui lòng nhập URL đúng định dạng (ví dụ: https://example.com)")
                website_input = None
            else:
                st.success(f"✅ URL hợp lệ: {website_input}")
    
    else:  # Natural language prompt
        website_input = st.text_area(
            "Nhập yêu cầu bằng tiếng Việt hoặc tiếng Anh:",
            placeholder="Ví dụ: Tôi muốn lấy tin từ vnexpress hoặc Crawl dữ liệu từ techcrunch.com/startups",
            height=100,
            help="Nhập yêu cầu tự nhiên, AI sẽ tự động hiểu và tìm website phù hợp"
        )
        
        if website_input:
            # Parse natural language to URL
            parsed_url = parse_natural_language_prompt(website_input)
            if parsed_url:
                st.success(f"✅ AI đã hiểu yêu cầu: {parsed_url}")
                website_input = parsed_url
            else:
                st.warning("⚠️ AI không thể hiểu yêu cầu. Vui lòng thử lại với prompt rõ ràng hơn.")
                website_input = None
    
    # Advanced options
    with st.expander("⚙️ Tùy chọn nâng cao"):
        col1, col2, col3 = st.columns(3)
        with col1:
            max_articles = st.slider("Số bài báo tối đa:", min_value=5, max_value=50, value=20)
        with col2:
            save_to_db = st.checkbox("💾 Tự động lưu vào Database", value=False, help="Nếu bỏ chọn, bạn sẽ có thể xem xét dữ liệu trước khi lưu")
        with col3:
            auto_process = st.checkbox("🧠 Tự động phân tích nội dung", value=True, help="Tự động trích xuất thông tin funding")
    
    # Crawl button
    if st.button("🚀 AI Auto-Discovery & Crawl", type="primary", disabled=not website_input):
        if website_input:
            with st.spinner("🤖 AI đang phân tích website..."):
                try:
                    # Import AI Auto-Discovery
                    from ai_auto_discovery import auto_crawl_website_async
                    
                    # Step 1: Analyze website
                    st.info("🔍 Đang phân tích cấu trúc website...")
                    
                    # Step 2: Auto-crawl
                    results = asyncio.run(auto_crawl_website_async(website_input, max_articles))
                    
                    if results and not results[0].get('error'):
                        st.success(f"✅ AI đã crawl thành công {len(results)} bài báo!")
                        
                        # Display results summary
                        successful = [r for r in results if r.get('success')]
                        st.info(f"📊 Kết quả: {len(successful)} thành công / {len(results)} tổng cộng")
                        
                        # Display results in table format
                        if successful:
                            if auto_process:
                                # Auto-process with LLM
                                with st.spinner("🧠 AI đang phân tích nội dung..."):
                                    processed_results = asyncio.run(process_auto_discovered_articles(successful))
                                    if processed_results:
                                        st.success("✅ Đã phân tích nội dung thành công!")
                                        display_company_data(processed_results, show_save_button=not save_to_db, save_to_db=save_to_db)
                                        
                                        # Auto-save to database if requested
                                        if save_to_db and processed_results:
                                            from db import insert_many_companies
                                            num_inserted = insert_many_companies(processed_results)
                                            st.success(f"💾 Đã tự động lưu {num_inserted} bản ghi vào database!")
                                            
                                            # Auto-refresh cache
                                            st.info("🔄 Đang cập nhật dữ liệu...")
                                            st.cache_data.clear()
                                            st.rerun()
                                    else:
                                        st.warning("⚠️ Không thể phân tích nội dung. Hiển thị dữ liệu thô...")
                                        display_raw_results(successful)
                            else:
                                # Display raw results
                                display_raw_results(successful)
                                
                                # Manual process option
                                if st.button("🧠 Phân tích nội dung với AI"):
                                    with st.spinner("AI đang phân tích nội dung..."):
                                        processed_results = asyncio.run(process_auto_discovered_articles(successful))
                                        if processed_results:
                                            st.success("✅ Đã phân tích nội dung thành công!")
                                            display_company_data(processed_results)
                                            
                                            # Save to database if requested
                                            if save_to_db and processed_results:
                                                from db import insert_many_companies
                                                num_inserted = insert_many_companies(processed_results)
                                                st.success(f"💾 Đã tự động lưu {num_inserted} bản ghi vào database!")
                        
                        # Show failed results
                        failed_results = [r for r in results if not r.get('success')]
                        if failed_results:
                            with st.expander(f"⚠️ {len(failed_results)} kết quả thất bại"):
                                for i, result in enumerate(failed_results):
                                    st.error(f"**{i+1}. {result.get('url', 'URL không xác định')}**: {result.get('error')}")
                    else:
                        error_msg = results[0].get('error') if results else "Không có kết quả"
                        
                        # Check if it's a bot blocking error
                        if "chặn bot" in error_msg.lower() or "bot blocked" in error_msg.lower() or "403" in error_msg:
                            st.error(f"🚫 **Bot bị chặn**: {error_msg}")
                            
                            # Show bot blocking solutions
                            with st.expander("🔧 Giải pháp khắc phục bot blocking"):
                                st.markdown("""
                                **Website đang chặn bot. Thử các giải pháp sau:**
                                
                                🔄 **1. Thử lại sau:**
                                - Đợi 5-10 phút rồi thử lại
                                - Website có thể tạm thời chặn do quá nhiều request
                                
                                🌐 **2. Sử dụng VPN:**
                                - Thay đổi IP address
                                - Sử dụng VPN khác nhau
                                
                                ⏰ **3. Giảm tốc độ:**
                                - Giảm số bài báo tối đa
                                - Thêm delay giữa các request
                                
                                🎯 **4. Thử website khác:**
                                - Website này có thể có chính sách chặn bot nghiêm ngặt
                                - Thử nguồn tin tương tự khác
                                
                                📧 **5. Liên hệ admin:**
                                - Nếu cần crawl thường xuyên, liên hệ website để xin permission
                                """)
                        else:
                            st.error(f"❌ AI Auto-Discovery thất bại: {error_msg}")
                        
                        # Provide general suggestions
                        st.markdown("### 💡 Gợi ý khắc phục:")
                        st.markdown("""
                        1. **Kiểm tra URL**: Đảm bảo URL đúng và website có thể truy cập
                        2. **Thử URL khác**: Thử với URL cụ thể hơn (ví dụ: /news thay vì homepage)
                        3. **Kiểm tra kết nối**: Đảm bảo có kết nối internet ổn định
                        4. **Thử lại sau**: Một số website có thể tạm thời không khả dụng
                        5. **Sử dụng VPN**: Nếu bị chặn bot, thử sử dụng VPN
                        """)
                        
                except Exception as e:
                    st.error(f"❌ Lỗi: {str(e)}")
                    logger.error(f"AI Auto-Discovery error: {e}")
        else:
            st.warning("Vui lòng nhập URL website hoặc yêu cầu hợp lệ")

async def process_auto_discovered_articles(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Process auto-discovered articles with LLM to extract funding information"""
    from llm_utils import extract_structured_data_llm
    from utils.data_normalizer import normalize_company_name, normalize_currency_amount, normalize_funding_round
    
    processed_results = []
    
    for article in articles:
        try:
            content = article.get('content', '')
            if not content:
                continue
            
            # Use LLM to extract funding information
            extracted_data = await asyncio.to_thread(extract_structured_data_llm, content)
            
            if extracted_data and extracted_data.get('company_name'):
                # Normalize data
                company_name = normalize_company_name(extracted_data.get('company_name'))
                
                amount_raised = extracted_data.get('amount_raised')
                if amount_raised:
                    normalized_amount, _ = normalize_currency_amount(str(amount_raised))
                    amount_raised = normalized_amount
                
                funding_round = extracted_data.get('funding_round')
                if funding_round:
                    funding_round = normalize_funding_round(funding_round)
                
                processed_results.append({
                    'raised_date': article.get('published_date'),
                    'company_name': company_name,
                    'industry': extracted_data.get('industry'),
                    'ceo_name': extracted_data.get('ceo_name'),
                    'procurement_name': extracted_data.get('procurement_name'),
                    'purchasing_name': extracted_data.get('purchasing_name'),
                    'manager_name': extracted_data.get('manager_name'),
                    'amount_raised': amount_raised,
                    'funding_round': funding_round,
                    'source': article.get('source', 'Auto-Discovered'),
                    'website': 'N/A',
                    'linkedin': 'N/A',
                    'article_url': article.get('url')
                })
        
        except Exception as e:
            logger.warning(f"Failed to process article {article.get('url')}: {e}")
            continue
    
    return processed_results

def is_valid_url(url: str) -> bool:
    """Validate if input is a valid URL"""
    import re
    from urllib.parse import urlparse
    
    # Check if it's a valid URL format
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False
    
    # Additional regex check for common patterns
    url_pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    return bool(url_pattern.match(url))

def display_raw_results(results: List[Dict[str, Any]]):
    """Display raw crawled results in a simple format"""
    if not results:
        st.warning("Không có dữ liệu để hiển thị")
        return
    
    # Create a simple table
    data = []
    for result in results:
        data.append({
            'Title': result.get('title', 'N/A'),
            'URL': result.get('url', 'N/A'),
            'Date': result.get('published_date', 'N/A'),
            'Source': result.get('source', 'N/A'),
            'Content Length': len(result.get('content', ''))
        })
    
    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True)
    
    # Show content preview
    if st.checkbox("👀 Xem nội dung mẫu"):
        for i, result in enumerate(results[:3]):  # Show first 3
            with st.expander(f"📄 {result.get('title', 'No title')}"):
                st.markdown(f"**URL:** {result.get('url')}")
                st.markdown(f"**Date:** {result.get('published_date')}")
                st.markdown(f"**Content:**")
                content = result.get('content', '')
                st.text(content[:500] + "..." if len(content) > 500 else content)

if __name__ == "__main__":
    main()