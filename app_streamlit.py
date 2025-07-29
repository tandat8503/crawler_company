import streamlit as st
import pandas as pd
import sqlite3
import os
import sys
from datetime import datetime, timedelta
from utils.logger import logger
from db import get_connection, init_db, get_companies

# Page configuration
st.set_page_config(
    page_title="Company Funding News Dashboard",
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
        text-align: center;
        color: #1f77b4;
        margin-bottom: 2rem;
    }
    .sub-header {
        font-size: 1.5rem;
        font-weight: bold;
        color: #2c3e50;
        margin-bottom: 1rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
        margin: 0.5rem 0;
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
    .info-message {
        background-color: #d1ecf1;
        color: #0c5460;
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid #bee5eb;
    }
    .stButton > button {
        width: 100%;
        margin: 0.5rem 0;
        padding: 0.75rem;
        font-size: 1.1rem;
        border-radius: 0.5rem;
    }
    .sidebar .sidebar-content {
        background-color: #f8f9fa;
    }
    th, td {
        text-align: center !important;
        vertical-align: middle !important;
    }
    .home-stats {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 2rem;
        border-radius: 1rem;
        margin: 1rem 0;
    }
    .feature-card {
        background-color: #ffffff;
        border: 2px solid #e9ecef;
        border-radius: 1rem;
        padding: 1.5rem;
        margin: 1rem 0;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        transition: transform 0.2s;
    }
    .feature-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(0, 0, 0, 0.15);
    }
    .nav-button {
        background: linear-gradient(135deg, #1f77b4 0%, #2c3e50 100%);
        color: white;
        border: none;
        border-radius: 0.5rem;
        padding: 1rem 2rem;
        font-size: 1.1rem;
        font-weight: bold;
        cursor: pointer;
        transition: all 0.3s ease;
        text-decoration: none;
        display: inline-block;
        margin: 0.5rem;
    }
    .nav-button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = datetime.now()
if 'current_page' not in st.session_state:
    st.session_state.current_page = "home"

def init_database():
    """Initialize database"""
    try:
        init_db()
        return True
    except Exception as e:
        st.error(f"Database initialization failed: {e}")
        return False

def get_database_stats():
    """Get database statistics"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            
            # Total companies
            cursor.execute("SELECT COUNT(*) FROM companies")
            total_companies = cursor.fetchone()[0]
            
            # Companies by source
            cursor.execute("""
                SELECT source, COUNT(*) as count 
                FROM companies 
                GROUP BY source 
                ORDER BY count DESC
            """)
            companies_by_source = cursor.fetchall()
            
            # Recent companies (last 7 days)
            cursor.execute("""
                SELECT COUNT(*) FROM companies 
                WHERE date(raised_date) >= date('now', '-7 days')
            """)
            recent_companies = cursor.fetchone()[0]
            
            # Total funding amount
            cursor.execute("""
                SELECT SUM(CAST(amount_raised AS INTEGER)) as total_amount
                FROM companies 
                WHERE amount_raised IS NOT NULL AND amount_raised != ''
            """)
            total_funding = cursor.fetchone()[0] or 0
            
            return {
                'total_companies': total_companies,
                'companies_by_source': companies_by_source,
                'recent_companies': recent_companies,
                'total_funding': total_funding
            }
    except Exception as e:
        st.error(f"Error getting database stats: {e}")
        return None

def fetch_all_companies(limit=100):
    """Fetch all companies from database"""
    try:
        with get_connection() as conn:
            query = """
            SELECT * FROM companies 
            ORDER BY date(raised_date) DESC, id DESC 
            LIMIT ?
            """
            cursor = conn.cursor()
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        st.error(f"Error fetching companies: {e}")
        return []

def fetch_companies_with_filters(filters):
    """Fetch companies with various filters"""
    try:
        with get_connection() as conn:
            query = "SELECT * FROM companies WHERE 1=1"
            params = []
            
            if filters.get('source') and filters['source'] != "All":
                query += " AND source = ?"
                params.append(filters['source'])
            
            if filters.get('funding_round') and filters['funding_round'] != "All":
                query += " AND funding_round = ?"
                params.append(filters['funding_round'])
            
            if filters.get('start_date') and filters.get('end_date'):
                query += " AND date(raised_date) BETWEEN date(?) AND date(?)"
                params.extend([filters['start_date'], filters['end_date']])
            
            if filters.get('min_amount') and filters['min_amount'] > 0:
                query += " AND CAST(amount_raised AS INTEGER) >= ?"
                params.append(int(filters['min_amount']))
            
            if filters.get('max_amount') and filters['max_amount'] > 0:
                query += " AND CAST(amount_raised AS INTEGER) <= ?"
                params.append(int(filters['max_amount']))
            
            query += " ORDER BY date(raised_date) DESC, id DESC"
            
            if filters.get('limit'):
                query += " LIMIT ?"
                params.append(filters['limit'])
            
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            
            return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        st.error(f"Error fetching companies: {e}")
        return []

def search_companies(query, search_type="all"):
    """Search companies"""
    try:
        with get_connection() as conn:
            if search_type == "company":
                sql_query = "SELECT * FROM companies WHERE company_name LIKE ?"
                params = [f"%{query}%"]
            elif search_type == "article_url":
                sql_query = "SELECT * FROM companies WHERE article_url LIKE ?"
                params = [f"%{query}%"]
            else:  # all
                sql_query = """
                SELECT * FROM companies 
                WHERE company_name LIKE ? OR article_url LIKE ? OR website LIKE ? OR linkedin LIKE ?
                """
                params = [f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%"]
            
            sql_query += " ORDER BY date(raised_date) DESC, id DESC LIMIT 100"
            
            cursor = conn.cursor()
            cursor.execute(sql_query, params)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            
            return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        st.error(f"Error searching companies: {e}")
        return []

def make_clickable(url):
    """Make URL clickable in dataframe"""
    if not url or url.strip() == "":
        return ""
    return f'<a href="{url}" target="_blank">🔗 Link</a>'

def format_amount(amount):
    """Format amount with commas"""
    if not amount:
        return ""
    try:
        return f"${int(amount):,}"
    except:
        return str(amount)

def clear_database():
    """Clear all data from database"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM companies")
            conn.commit()
        return True
    except Exception as e:
        st.error(f"Error clearing database: {e}")
        return False

def home_page():
    """Home page with overview and navigation"""
    st.markdown('<h1 class="main-header">💰 Company Funding News Dashboard</h1>', unsafe_allow_html=True)
    
    # Get database stats
    stats = get_database_stats()
    
    if stats:
        # Overview stats
        st.markdown('<div class="home-stats">', unsafe_allow_html=True)
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("📊 Total Companies", stats['total_companies'])
        
        with col2:
            st.metric("🆕 Recent (7 days)", stats['recent_companies'])
        
        with col3:
            st.metric("💰 Total Funding", f"${stats['total_funding']:,}")
        
        with col4:
            if stats['total_companies'] > 0:
                avg_funding = stats['total_funding'] // stats['total_companies']
                st.metric("📈 Avg Funding", f"${avg_funding:,}")
            else:
                st.metric("📈 Avg Funding", "$0")
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Companies by source chart
        if stats['companies_by_source']:
            st.subheader("📊 Companies by Source")
            source_data = pd.DataFrame(stats['companies_by_source'], columns=['Source', 'Count'])
            st.bar_chart(source_data.set_index('Source'))
    
    # Navigation buttons
    st.markdown('<h2 class="sub-header">🚀 Quick Actions</h2>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown('<div class="feature-card">', unsafe_allow_html=True)
        st.markdown('<h3>🔍 Advanced Search & Filter</h3>', unsafe_allow_html=True)
        st.write("Search companies by name, URL, or keywords. Apply advanced filters by source, funding round, date range, and amount.")
        if st.button("🔍 Go to Search & Filter", key="nav_search"):
            st.session_state.current_page = "companies"
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown('<div class="feature-card">', unsafe_allow_html=True)
        st.markdown('<h3>📈 Analytics & Statistics</h3>', unsafe_allow_html=True)
        st.write("View detailed statistics, charts, and analytics about funding trends, company distribution, and market insights.")
        if st.button("📈 View Analytics", key="nav_stats"):
            st.session_state.current_page = "statistics"
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col2:
        st.markdown('<div class="feature-card">', unsafe_allow_html=True)
        st.markdown('<h3>⚙️ System Settings</h3>', unsafe_allow_html=True)
        st.write("Manage database, view system information, check logs, and configure application settings.")
        if st.button("⚙️ Open Settings", key="nav_settings"):
            st.session_state.current_page = "settings"
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown('<div class="feature-card">', unsafe_allow_html=True)
        st.markdown('<h3>🔄 Refresh Data</h3>', unsafe_allow_html=True)
        st.write("Refresh the current data and update statistics. Use this after running crawlers to see new data.")
        if st.button("🔄 Refresh Now", key="nav_refresh"):
            st.session_state.last_refresh = datetime.now()
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Recent companies table
    st.markdown('<h2 class="sub-header">📋 Recent Companies</h2>', unsafe_allow_html=True)
    
    companies = fetch_all_companies(50)  # Show last 50 companies
    
    if companies:
        df = pd.DataFrame(companies)
        
        # Format data
        if 'article_url' in df.columns:
            df['article_url'] = df['article_url'].apply(make_clickable)
        if 'website' in df.columns:
            df['website'] = df['website'].apply(make_clickable)
        if 'linkedin' in df.columns:
            df['linkedin'] = df['linkedin'].apply(make_clickable)
        if 'amount_raised' in df.columns:
            df['amount_raised'] = df['amount_raised'].apply(format_amount)
        
        # Select columns to display
        display_columns = ['raised_date', 'company_name', 'amount_raised', 'funding_round', 'source', 'website', 'linkedin', 'article_url']
        available_columns = [col for col in display_columns if col in df.columns]
        
        st.write(f"**Showing {len(companies)} most recent companies**")
        st.write(df[available_columns].to_html(escape=False, index=False), unsafe_allow_html=True)
        
        # Download all data
        csv_data = df.to_csv(index=False)
        st.download_button(
            label="📥 Download All Data (CSV)",
            data=csv_data,
            file_name=f"all_companies_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
        
        if st.button("📋 View All Companies with Filters"):
            st.session_state.current_page = "companies"
            st.rerun()
    else:
        st.info("No companies found in database. Run crawlers to collect data first.")

def companies_page():
    """Companies page with advanced filtering"""
    st.markdown('<h1 class="main-header">🔍 Search & Filter Companies</h1>', unsafe_allow_html=True)
    
    # Back to home button
    if st.button("🏠 Back to Home"):
        st.session_state.current_page = "home"
        st.rerun()
    
    st.header("📋 Company List")
    
    # Filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Source filter
        sources = ["All"] + [row[0] for row in get_database_stats()['companies_by_source']] if get_database_stats() else ["All"]
        selected_source = st.selectbox("Source", sources)
        
        # Funding round filter
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT funding_round 
                FROM companies 
                WHERE funding_round IS NOT NULL AND funding_round != ''
                ORDER BY funding_round
            """)
            funding_rounds = ["All"] + [row[0] for row in cursor.fetchall()]
        
        selected_round = st.selectbox("Funding Round", funding_rounds)
    
    with col2:
        # Date range
        start_date = st.date_input("Start Date", value=datetime.now().date() - timedelta(days=30))
        end_date = st.date_input("End Date", value=datetime.now().date())
    
    with col3:
        # Amount range
        min_amount = st.number_input("Min Amount ($)", min_value=0, value=0, step=100000)
        max_amount = st.number_input("Max Amount ($)", min_value=0, value=10000000, step=100000)
        
        limit = st.number_input("Limit", min_value=1, max_value=1000, value=100)
    
    # Apply filters
    filters = {
        'source': selected_source,
        'funding_round': selected_round,
        'start_date': str(start_date),
        'end_date': str(end_date),
        'min_amount': min_amount,
        'max_amount': max_amount,
        'limit': limit
    }
    
    # Fetch and display data
    companies = fetch_companies_with_filters(filters)
    
    if companies:
        df = pd.DataFrame(companies)
        
        # Format data
        if 'article_url' in df.columns:
            df['article_url'] = df['article_url'].apply(make_clickable)
        if 'website' in df.columns:
            df['website'] = df['website'].apply(make_clickable)
        if 'linkedin' in df.columns:
            df['linkedin'] = df['linkedin'].apply(make_clickable)
        if 'amount_raised' in df.columns:
            df['amount_raised'] = df['amount_raised'].apply(format_amount)
        
        # Select columns to display
        display_columns = ['raised_date', 'company_name', 'amount_raised', 'funding_round', 'source', 'website', 'linkedin', 'article_url']
        available_columns = [col for col in display_columns if col in df.columns]
        
        st.write(f"**Found {len(companies)} companies**")
        st.write(df[available_columns].to_html(escape=False, index=False), unsafe_allow_html=True)
        
        # Download button
        csv_data = df.to_csv(index=False)
        st.download_button(
            label="📥 Download Filtered CSV",
            data=csv_data,
            file_name=f"filtered_companies_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
    else:
        st.info("No companies found with the selected filters.")

def search_page():
    """Search page"""
    st.markdown('<h1 class="main-header">🔍 Search Companies</h1>', unsafe_allow_html=True)
    
    # Back to home button
    if st.button("🏠 Back to Home"):
        st.session_state.current_page = "home"
        st.rerun()
    
    st.header("🔍 Search Companies")
    
    # Search options
    col1, col2 = st.columns(2)
    
    with col1:
        search_query = st.text_input("Search query", placeholder="Enter company name, URL, or keywords...")
        search_type = st.selectbox("Search type", ["all", "company", "article_url"])
    
    with col2:
        search_source = st.selectbox("Filter by source", ["All"] + [row[0] for row in get_database_stats()['companies_by_source']] if get_database_stats() else ["All"])
        st.write("")
        search_button = st.button("🔍 Search", type="primary")
    
    if search_button and search_query:
        with st.spinner("Searching..."):
            results = search_companies(search_query, search_type)
            
            if results:
                df = pd.DataFrame(results)
                
                # Apply source filter
                if search_source != "All":
                    df = df[df['source'] == search_source]
                
                # Format data
                if 'article_url' in df.columns:
                    df['article_url'] = df['article_url'].apply(make_clickable)
                if 'website' in df.columns:
                    df['website'] = df['website'].apply(make_clickable)
                if 'linkedin' in df.columns:
                    df['linkedin'] = df['linkedin'].apply(make_clickable)
                if 'amount_raised' in df.columns:
                    df['amount_raised'] = df['amount_raised'].apply(format_amount)
                
                st.write(f"**Found {len(df)} results**")
                
                # Display results
                display_columns = ['raised_date', 'company_name', 'amount_raised', 'funding_round', 'source', 'website', 'linkedin', 'article_url']
                available_columns = [col for col in display_columns if col in df.columns]
                
                st.write(df[available_columns].to_html(escape=False, index=False), unsafe_allow_html=True)
                
                # Download search results
                csv_data = df.to_csv(index=False)
                st.download_button(
                    label="📥 Download Search Results",
                    data=csv_data,
                    file_name=f"search_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
            else:
                st.info("No results found.")

def statistics_page():
    """Statistics page"""
    st.markdown('<h1 class="main-header">📈 Analytics & Statistics</h1>', unsafe_allow_html=True)
    
    # Back to home button
    if st.button("🏠 Back to Home"):
        st.session_state.current_page = "home"
        st.rerun()
    
    st.header("📈 Statistics")
    
    stats = get_database_stats()
    if stats:
        # Key metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Companies", stats['total_companies'])
        
        with col2:
            st.metric("Recent (7 days)", stats['recent_companies'])
        
        with col3:
            st.metric("Total Funding", f"${stats['total_funding']:,}")
        
        with col4:
            # Calculate average funding
            if stats['total_companies'] > 0:
                avg_funding = stats['total_funding'] // stats['total_companies']
                st.metric("Avg Funding", f"${avg_funding:,}")
            else:
                st.metric("Avg Funding", "$0")
        
        # Charts
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Companies by Source")
            source_data = pd.DataFrame(stats['companies_by_source'], columns=['Source', 'Count'])
            st.bar_chart(source_data.set_index('Source'))
        
        with col2:
            st.subheader("Recent Activity")
            # Get daily counts for last 30 days
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT date(raised_date) as date, COUNT(*) as count
                    FROM companies 
                    WHERE date(raised_date) >= date('now', '-30 days')
                    GROUP BY date(raised_date)
                    ORDER BY date(raised_date)
                """)
                daily_data = cursor.fetchall()
            
            if daily_data:
                daily_df = pd.DataFrame(daily_data, columns=['Date', 'Count'])
                daily_df['Date'] = pd.to_datetime(daily_df['Date'])
                st.line_chart(daily_df.set_index('Date'))
            else:
                st.info("No recent activity data available.")
    else:
        st.error("Unable to load statistics.")

def settings_page():
    """Settings page"""
    st.markdown('<h1 class="main-header">⚙️ System Settings</h1>', unsafe_allow_html=True)
    
    # Back to home button
    if st.button("🏠 Back to Home"):
        st.session_state.current_page = "home"
        st.rerun()
    
    st.header("⚙️ Settings")
    
    st.subheader("Database Information")
    
    # Database file info
    db_path = "companies.db"
    if os.path.exists(db_path):
        file_size = os.path.getsize(db_path)
        file_size_mb = file_size / (1024 * 1024)
        st.write(f"**Database File:** {db_path}")
        st.write(f"**File Size:** {file_size_mb:.2f} MB")
        st.write(f"**Last Modified:** {datetime.fromtimestamp(os.path.getmtime(db_path)).strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        st.warning("Database file not found.")
    
    st.subheader("System Information")
    st.write(f"**Python Version:** {sys.version}")
    st.write(f"**Working Directory:** {os.getcwd()}")
    st.write(f"**Current Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Show recent logs
    st.subheader("Recent Logs")
    log_file = os.path.join('logs', f'crawler_{datetime.now().strftime("%Y%m%d")}.log')
    if os.path.exists(log_file):
        with open(log_file, 'r') as f:
            logs = f.readlines()[-20:]  # Last 20 lines
            st.code(''.join(logs), language='text')
    else:
        st.info("No log file found for today.")

# Sidebar
def sidebar():
    """Sidebar with controls"""
    with st.sidebar:
        st.header("🔧 Control Panel")
        
        # Database info
        st.subheader("📊 Database Info")
        stats = get_database_stats()
        if stats:
            st.metric("Total Companies", stats['total_companies'])
            st.metric("Recent (7 days)", stats['recent_companies'])
            st.metric("Total Funding", f"${stats['total_funding']:,}")
            
            st.write("**Companies by Source:**")
            for source, count in stats['companies_by_source']:
                st.write(f"• {source}: {count}")
        
        st.markdown("---")
        
        # Database management
        st.subheader("🗄️ Database Management")
        
        if st.button("🗑️ Clear All Data", type="secondary"):
            if clear_database():
                st.success("Database cleared successfully!")
                st.rerun()
        
        if st.button("🔄 Refresh Data"):
            st.session_state.last_refresh = datetime.now()
            st.rerun()
        
        st.markdown("---")
        
        # System info
        st.subheader("ℹ️ System Info")
        st.write(f"**Last Refresh:** {st.session_state.last_refresh.strftime('%Y-%m-%d %H:%M:%S')}")
        st.write(f"**Database:** companies.db")
        st.write(f"**Working Dir:** {os.getcwd()}")

# Main app
def main():
    # Initialize database
    if not init_database():
        st.stop()
    
    # Sidebar
    sidebar()
    
    # Main content based on current page
    if st.session_state.current_page == "home":
        home_page()
    elif st.session_state.current_page == "companies":
        companies_page()
    elif st.session_state.current_page == "search":
        search_page()
    elif st.session_state.current_page == "statistics":
        statistics_page()
    elif st.session_state.current_page == "settings":
        settings_page()

if __name__ == "__main__":
    main()