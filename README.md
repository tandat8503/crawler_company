# Agent FundRadar

Tìm kiếm các công ty mới được đầu tư ở các thị trường (US, EU, LA, ...), trích xuất thông tin bằng SerpAPI + OpenAI.

## 1. Cài đặt

```bash
cd agent_fundradar
pip install -r requirements.txt
```

## 2. Cấu hình API Key

- Tạo file `.env` (nếu muốn) hoặc sửa trực tiếp trong `config.py`:
  - `SERPAPI_API_KEY`: Lấy tại https://serpapi.com/
  - `OPENAI_API_KEY`: Lấy tại https://platform.openai.com/

Ví dụ file `.env`:

```
SERPAPI_API_KEY=your_serpapi_key
OPENAI_API_KEY=your_openai_key
```

## 3. Chạy chương trình

```bash
python main.py
```

Sau đó nhập thị trường (US, Europe, Asia, ...), năm, số lượng kết quả.

## 4. Cấu trúc project

- `main.py`: Chạy pipeline chính
- `search.py`: Tìm kiếm công ty mới được đầu tư bằng SerpAPI
- `extract.py`: Trích xuất thông tin công ty bằng OpenAI
- `config.py`: Lưu API keys

## 5. Lưu ý

- Sử dụng hợp lý số lượng request để tránh bị giới hạn API.
- Kết quả trích xuất phụ thuộc vào chất lượng snippet và khả năng của LLM.
