import streamlit as st
import pandas as pd
import requests
from datetime import datetime

API_URL = "http://localhost:8000"

st.set_page_config(page_title="Company Funding News", layout="wide")
st.title("Company Funding News")

# Thêm CSS căn giữa header và cell
st.markdown(
    '''
    <style>
    th, td {
        text-align: center !important;
        vertical-align: middle !important;
    }
    </style>
    ''',
    unsafe_allow_html=True
)

def fetch_companies(start_date=None, end_date=None):
    params = {}
    if start_date:
        params['start_date'] = start_date
    if end_date:
        params['end_date'] = end_date
    resp = requests.get(f"{API_URL}/companies", params=params)
    if resp.status_code == 200:
        return resp.json()
    return []

def make_clickable(url):
    if not url or url.strip() == "":
        return ""
    return f'<a href="{url}" target="_blank">{url}</a>'

# Lấy min/max date từ dữ liệu (nếu có)
companies = fetch_companies()
df = pd.DataFrame(companies)
if not df.empty and 'raised_date' in df.columns:
    df['raised_date_parsed'] = pd.to_datetime(df['raised_date'], errors='coerce')
    if df['raised_date_parsed'].notna().any():
        min_date = df['raised_date_parsed'].min().date()
        max_date = df['raised_date_parsed'].max().date()
    else:
        min_date = max_date = datetime.today().date()
else:
    min_date = max_date = datetime.today().date()

col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("From raised date", value=min_date)
with col2:
    end_date = st.date_input("To raised date", value=max_date)

# Lấy lại dữ liệu theo filter ngày
companies = fetch_companies(str(start_date), str(end_date))
df = pd.DataFrame(companies)

if not df.empty:
    df['article_url'] = df['article_url'].apply(make_clickable)
    df['website'] = df['website'].apply(make_clickable)
    df['linkedin'] = df['linkedin'].apply(make_clickable)
    fields = [
        "raised_date", "company_name", "website", "linkedin", "article_url", "amount_raised", "funding_round", "crawl_date"
    ]
    show_df = df[fields] if all(f in df.columns for f in fields) else df
    st.write("### Danh sách công ty được raise fund (theo filter ngày)")
    st.write("(Click vào 'Link' để xem bài báo gốc)")
    st.write(
        show_df.to_html(escape=False, index=False),
        unsafe_allow_html=True
    )
    st.download_button(
        label="Download filtered CSV",
        data=show_df.to_csv(index=False).encode("utf-8"),
        file_name="filtered_companies.csv",
        mime="text/csv"
    )
else:
    st.info("Không có dữ liệu trong khoảng ngày đã chọn.")

# Search Tavily
st.write("---")
st.subheader("Tìm kiếm thông tin với Tavily")
search_query = st.text_input("Nhập từ khóa tìm kiếm (tiếng Anh)")
if search_query:
    with st.spinner("Đang tìm kiếm với Tavily..."):
        resp = requests.post(f"{API_URL}/search", json={"query": search_query, "max_results": 5})
        if resp.status_code == 200:
            result = resp.json()
            if 'results' in result:
                st.write("### Kết quả tìm kiếm:")
                for i, item in enumerate(result['results'], 1):
                    st.markdown(f"**{i}. [{item.get('title', 'No Title')}]({item.get('url', '')})**")
                    st.write(item.get('content', ''))
                    st.write('---')
            else:
                st.warning("Không có kết quả hoặc lỗi định dạng từ Tavily.")
        else:
            st.error(f"Lỗi khi gọi Tavily: {resp.text}")