import streamlit as st
import pandas as pd
import os

CSV_FILE = os.path.join(os.path.dirname(__file__), 'companies.csv')

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

if not os.path.exists(CSV_FILE):
    st.warning("No data found. Please run the crawler first.")
    st.stop()

try:
    df = pd.read_csv(CSV_FILE, dtype=str)
except Exception as e:
    st.error(f"Error reading CSV: {e}")
    st.stop()

fields = ["raised_date", "company_name", "website", "linkedin", "article_url", "source", "crawl_date"]
for col in fields:
    if col not in df.columns:
        df[col] = ""
df = df[fields]

# Ép kiểu ngày cho raised_date, bỏ qua giá trị không hợp lệ
df["raised_date_parsed"] = pd.to_datetime(df["raised_date"], errors='coerce')

# Nếu không có ngày nào hợp lệ, dùng hôm nay làm mặc định
if df["raised_date_parsed"].notna().any():
    min_date = df["raised_date_parsed"].min().date()
    max_date = df["raised_date_parsed"].max().date()
else:
    min_date = max_date = pd.Timestamp.today().date()

col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("From raised date", value=min_date)
with col2:
    end_date = st.date_input("To raised date", value=max_date)

mask = (
    df["raised_date_parsed"] >= pd.to_datetime(start_date)
) & (
    df["raised_date_parsed"] <= pd.to_datetime(end_date)
)
filtered_df = df[mask]

filtered_df = filtered_df.sort_values(by="raised_date_parsed", ascending=False)

def make_clickable(url):
    if pd.isna(url) or url.strip() == "":
        return ""
    return f'<a href="{url}" target="_blank">{url}</a>'

show_df = filtered_df.copy()
show_df["article_url"] = show_df["article_url"].apply(make_clickable)
show_df["website"] = show_df["website"].apply(make_clickable)
show_df["linkedin"] = show_df["linkedin"].apply(make_clickable)
show_df = show_df[fields]  # Đảm bảo đúng thứ tự

st.write("### Danh sách công ty được raise fund (7 ngày gần nhất)")
st.write("(Click vào 'Link' để xem bài báo gốc)")
st.write(
    show_df.to_html(escape=False, index=False),
    unsafe_allow_html=True
)

st.download_button(
    label="Download filtered CSV",
    data=filtered_df[fields].to_csv(index=False).encode("utf-8"),
    file_name="filtered_companies.csv",
    mime="text/csv"
)