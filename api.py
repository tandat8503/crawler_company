from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List, Dict, Any
from datetime import datetime, date, timedelta
import sqlite3
from contextlib import closing
import os
from utils.logger import logger
from db import get_connection, get_companies

app = FastAPI(
    title="Company Funding News API",
    description="API for accessing company funding data from multiple sources",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = os.path.join(os.path.dirname(__file__), 'companies.db')

def execute_query(query: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """Execute database query and return results as list of dictionaries"""
    try:
        with closing(get_connection()) as conn:
            c = conn.cursor()
            c.execute(query, params)
            rows = c.fetchall()
            columns = [desc[0] for desc in c.description]
            return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        logger.error(f"Database query error: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Company Funding News API",
        "version": "1.0.0",
        "endpoints": {
            "get_companies": "/api/companies",
            "get_companies_by_source": "/api/companies/source/{source}",
            "get_companies_by_date_range": "/api/companies/date-range",
            "get_companies_by_amount_range": "/api/companies/amount-range",
            "get_companies_by_funding_round": "/api/companies/round/{round_type}",
            "search_companies": "/api/companies/search",
            "get_sources": "/api/sources",
            "get_funding_rounds": "/api/funding-rounds",
            "get_statistics": "/api/statistics",
            "get_recent_funding": "/api/recent-funding"
        }
    }

@app.get("/api/companies")
async def get_companies_api(
    limit: Optional[int] = Query(100, description="Number of records to return"),
    offset: Optional[int] = Query(0, description="Number of records to skip"),
    source: Optional[str] = Query(None, description="Filter by source (TechCrunch, Finsmes, etc.)"),
    funding_round: Optional[str] = Query(None, description="Filter by funding round"),
    min_amount: Optional[str] = Query(None, description="Minimum funding amount"),
    max_amount: Optional[str] = Query(None, description="Maximum funding amount"),
    currency: Optional[str] = Query(None, description="Filter by currency (USD, EUR, etc.)"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)")
):
    """
    Get companies with various filters
    """
    try:
        # Build query
        query = "SELECT * FROM companies WHERE 1=1"
        params = []
        
        if source:
            query += " AND source = ?"
            params.append(source)
        
        if funding_round:
            query += " AND funding_round = ?"
            params.append(funding_round)
        
        if currency:
            query += " AND currency = ?"
            params.append(currency)
        
        if start_date and end_date:
            query += " AND date(raised_date) BETWEEN date(?) AND date(?)"
            params.extend([start_date, end_date])
        elif start_date:
            query += " AND date(raised_date) >= date(?)"
            params.append(start_date)
        elif end_date:
            query += " AND date(raised_date) <= date(?)"
            params.append(end_date)
        
        if min_amount:
            query += " AND CAST(amount_raised AS INTEGER) >= ?"
            params.append(int(min_amount))
        
        if max_amount:
            query += " AND CAST(amount_raised AS INTEGER) <= ?"
            params.append(int(max_amount))
        
        # Add ordering and pagination
        query += " ORDER BY date(raised_date) DESC, id DESC"
        query += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        results = execute_query(query, tuple(params))
        
        return {
            "success": True,
            "data": results,
            "count": len(results),
            "limit": limit,
            "offset": offset,
            "filters": {
                "source": source,
                "funding_round": funding_round,
                "min_amount": min_amount,
                "max_amount": max_amount,
                "currency": currency,
                "start_date": start_date,
                "end_date": end_date
            }
        }
    except Exception as e:
        logger.error(f"Error in get_companies_api: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/companies/source/{source}")
async def get_companies_by_source(
    source: str,
    limit: Optional[int] = Query(100, description="Number of records to return"),
    offset: Optional[int] = Query(0, description="Number of records to skip")
):
    """
    Get companies by specific source (TechCrunch, Finsmes, etc.)
    """
    try:
        query = """
        SELECT * FROM companies 
        WHERE source = ? 
        ORDER BY date(raised_date) DESC, id DESC 
        LIMIT ? OFFSET ?
        """
        results = execute_query(query, (source, limit, offset))
        
        return {
            "success": True,
            "source": source,
            "data": results,
            "count": len(results),
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        logger.error(f"Error in get_companies_by_source: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/companies/date-range")
async def get_companies_by_date_range(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    source: Optional[str] = Query(None, description="Filter by source"),
    limit: Optional[int] = Query(100, description="Number of records to return"),
    offset: Optional[int] = Query(0, description="Number of records to skip")
):
    """
    Get companies within a specific date range
    """
    try:
        query = """
        SELECT * FROM companies 
        WHERE date(raised_date) BETWEEN date(?) AND date(?)
        """
        params = [start_date, end_date]
        
        if source:
            query += " AND source = ?"
            params.append(source)
        
        query += " ORDER BY date(raised_date) DESC, id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        results = execute_query(query, tuple(params))
        
        return {
            "success": True,
            "date_range": {"start_date": start_date, "end_date": end_date},
            "source": source,
            "data": results,
            "count": len(results),
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        logger.error(f"Error in get_companies_by_date_range: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/companies/amount-range")
async def get_companies_by_amount_range(
    min_amount: str = Query(..., description="Minimum amount"),
    max_amount: str = Query(..., description="Maximum amount"),
    currency: Optional[str] = Query("USD", description="Currency filter"),
    source: Optional[str] = Query(None, description="Filter by source"),
    limit: Optional[int] = Query(100, description="Number of records to return"),
    offset: Optional[int] = Query(0, description="Number of records to skip")
):
    """
    Get companies within a specific funding amount range
    """
    try:
        query = """
        SELECT * FROM companies 
        WHERE CAST(amount_raised AS INTEGER) BETWEEN ? AND ?
        AND currency = ?
        """
        params = [int(min_amount), int(max_amount), currency]
        
        if source:
            query += " AND source = ?"
            params.append(source)
        
        query += " ORDER BY CAST(amount_raised AS INTEGER) DESC, date(raised_date) DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        results = execute_query(query, tuple(params))
        
        return {
            "success": True,
            "amount_range": {"min_amount": min_amount, "max_amount": max_amount, "currency": currency},
            "source": source,
            "data": results,
            "count": len(results),
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        logger.error(f"Error in get_companies_by_amount_range: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/companies/round/{round_type}")
async def get_companies_by_funding_round(
    round_type: str,
    source: Optional[str] = Query(None, description="Filter by source"),
    limit: Optional[int] = Query(100, description="Number of records to return"),
    offset: Optional[int] = Query(0, description="Number of records to skip")
):
    """
    Get companies by funding round type
    """
    try:
        query = """
        SELECT * FROM companies 
        WHERE funding_round = ?
        """
        params = [round_type]
        
        if source:
            query += " AND source = ?"
            params.append(source)
        
        query += " ORDER BY date(raised_date) DESC, id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        results = execute_query(query, tuple(params))
        
        return {
            "success": True,
            "funding_round": round_type,
            "source": source,
            "data": results,
            "count": len(results),
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        logger.error(f"Error in get_companies_by_funding_round: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/companies/search")
async def search_companies(
    q: str = Query(..., description="Search query"),
    search_type: str = Query("company", description="Search type: company, article_url, or all"),
    source: Optional[str] = Query(None, description="Filter by source"),
    limit: Optional[int] = Query(100, description="Number of records to return"),
    offset: Optional[int] = Query(0, description="Number of records to skip")
):
    """
    Search companies by name, article URL, or all fields
    """
    try:
        if search_type == "company":
            query = """
            SELECT * FROM companies 
            WHERE company_name LIKE ?
            """
            params = [f"%{q}%"]
        elif search_type == "article_url":
            query = """
            SELECT * FROM companies 
            WHERE article_url LIKE ?
            """
            params = [f"%{q}%"]
        else:  # all
            query = """
            SELECT * FROM companies 
            WHERE company_name LIKE ? OR article_url LIKE ? OR website LIKE ? OR linkedin LIKE ?
            """
            params = [f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%"]
        
        if source:
            query += " AND source = ?"
            params.append(source)
        
        query += " ORDER BY date(raised_date) DESC, id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        results = execute_query(query, tuple(params))
        
        return {
            "success": True,
            "query": q,
            "search_type": search_type,
            "source": source,
            "data": results,
            "count": len(results),
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        logger.error(f"Error in search_companies: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sources")
async def get_sources():
    """
    Get list of all available sources
    """
    try:
        query = """
        SELECT DISTINCT source, COUNT(*) as count 
        FROM companies 
        GROUP BY source 
        ORDER BY count DESC
        """
        results = execute_query(query)
        
        return {
            "success": True,
            "sources": results
        }
    except Exception as e:
        logger.error(f"Error in get_sources: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/funding-rounds")
async def get_funding_rounds():
    """
    Get list of all available funding rounds
    """
    try:
        query = """
        SELECT DISTINCT funding_round, COUNT(*) as count 
        FROM companies 
        WHERE funding_round IS NOT NULL AND funding_round != ''
        GROUP BY funding_round 
        ORDER BY count DESC
        """
        results = execute_query(query)
        
        return {
            "success": True,
            "funding_rounds": results
        }
    except Exception as e:
        logger.error(f"Error in get_funding_rounds: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/statistics")
async def get_statistics(
    source: Optional[str] = Query(None, description="Filter by source"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)")
):
    """
    Get statistics about the funding data
    """
    try:
        # Build base query
        where_clause = "WHERE 1=1"
        params = []
        
        if source:
            where_clause += " AND source = ?"
            params.append(source)
        
        if start_date and end_date:
            where_clause += " AND date(raised_date) BETWEEN date(?) AND date(?)"
            params.extend([start_date, end_date])
        
        # Total companies
        total_query = f"SELECT COUNT(*) as total FROM companies {where_clause}"
        total_result = execute_query(total_query, tuple(params))
        total_companies = total_result[0]['total'] if total_result else 0
        
        # Total funding amount
        amount_query = f"""
        SELECT 
            SUM(CAST(amount_raised AS INTEGER)) as total_amount,
            currency,
            COUNT(*) as count
        FROM companies 
        {where_clause} 
        AND amount_raised IS NOT NULL AND amount_raised != ''
        GROUP BY currency
        ORDER BY total_amount DESC
        """
        amount_results = execute_query(amount_query, tuple(params))
        
        # Companies by source
        source_query = f"""
        SELECT source, COUNT(*) as count 
        FROM companies 
        {where_clause} 
        GROUP BY source 
        ORDER BY count DESC
        """
        source_results = execute_query(source_query, tuple(params))
        
        # Companies by funding round
        round_query = f"""
        SELECT funding_round, COUNT(*) as count 
        FROM companies 
        {where_clause} 
        AND funding_round IS NOT NULL AND funding_round != ''
        GROUP BY funding_round 
        ORDER BY count DESC
        """
        round_results = execute_query(round_query, tuple(params))
        
        # Recent activity (last 30 days)
        recent_query = f"""
        SELECT COUNT(*) as recent_count 
        FROM companies 
        {where_clause} 
        AND date(raised_date) >= date('now', '-30 days')
        """
        recent_result = execute_query(recent_query, tuple(params))
        recent_count = recent_result[0]['recent_count'] if recent_result else 0
        
        return {
            "success": True,
            "statistics": {
                "total_companies": total_companies,
                "total_funding_by_currency": amount_results,
                "companies_by_source": source_results,
                "companies_by_funding_round": round_results,
                "recent_companies_30_days": recent_count,
                "filters": {
                    "source": source,
                    "start_date": start_date,
                    "end_date": end_date
                }
            }
        }
    except Exception as e:
        logger.error(f"Error in get_statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/recent-funding")
async def get_recent_funding(
    days: int = Query(7, description="Number of days to look back"),
    source: Optional[str] = Query(None, description="Filter by source"),
    limit: Optional[int] = Query(20, description="Number of records to return")
):
    """
    Get recent funding announcements
    """
    try:
        query = """
        SELECT * FROM companies 
        WHERE date(raised_date) >= date('now', '-{} days')
        """.format(days)
        params = []
        
        if source:
            query += " AND source = ?"
            params.append(source)
        
        query += " ORDER BY date(raised_date) DESC, id DESC LIMIT ?"
        params.append(limit)
        
        results = execute_query(query, tuple(params))
        
        return {
            "success": True,
            "days_back": days,
            "source": source,
            "data": results,
            "count": len(results)
        }
    except Exception as e:
        logger.error(f"Error in get_recent_funding: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/companies/{company_id}")
async def get_company_by_id(company_id: int):
    """
    Get a specific company by ID
    """
    try:
        query = "SELECT * FROM companies WHERE id = ?"
        results = execute_query(query, (company_id,))
        
        if not results:
            raise HTTPException(status_code=404, detail="Company not found")
        
        return {
            "success": True,
            "data": results[0]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_company_by_id: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 