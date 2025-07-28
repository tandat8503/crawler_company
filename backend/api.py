from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from .db import get_companies
import requests
import os

from . import config
TAVILY_API_KEY = config.TAVILY_API_KEY
TAVILY_API_URL = "https://api.tavily.com/search"

app = FastAPI()

# Cho phép CORS cho mọi nguồn (phục vụ frontend local)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Company(BaseModel):
    id: int
    raised_date: Optional[str]
    company_name: Optional[str]
    website: Optional[str]
    linkedin: Optional[str]
    article_url: Optional[str]
    amount_raised: Optional[str]
    funding_round: Optional[str]
    crawl_date: Optional[str]

class SearchRequest(BaseModel):
    query: str
    max_results: Optional[int] = 5

@app.get("/companies", response_model=List[Company])
def get_companies_api(
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD")
):
    return get_companies(start_date, end_date)

@app.post("/search")
def search_tavily(req: SearchRequest):
    headers = {"Authorization": f"Bearer {TAVILY_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "query": req.query,
        "max_results": req.max_results or 5
    }
    try:
        resp = requests.post(TAVILY_API_URL, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)} 