#!/usr/bin/env python3
"""
Test script để kiểm tra funding detection
"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.llm_utils import has_funding_keywords, is_funding_article_llm
from backend.utils.logger import logger

def test_funding_keywords():
    """Test hàm has_funding_keywords"""
    print("=== Testing Funding Keywords ===")
    
    # Test cases
    test_cases = [
        {
            "text": "21-year-old MIT dropouts raise $32M at $300M valuation led by Insight",
            "expected": True,
            "description": "Rõ ràng về funding"
        },
        {
            "text": "Company raises $10M in Series A funding round",
            "expected": True,
            "description": "Series A funding"
        },
        {
            "text": "Startup receives $5M investment from venture capitalists",
            "expected": True,
            "description": "Investment từ VCs"
        },
        {
            "text": "Company launches new product and announces partnership",
            "expected": False,
            "description": "Không phải funding"
        },
        {
            "text": "OpenAI agreed to pay Oracle $30B a year for data center services",
            "expected": False,
            "description": "Partnership, không phải funding"
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        result = has_funding_keywords(test_case["text"])
        status = "✅" if result == test_case["expected"] else "❌"
        print(f"{status} Test {i}: {test_case['description']}")
        print(f"   Text: {test_case['text']}")
        print(f"   Expected: {test_case['expected']}, Got: {result}")
        print()

def test_funding_article_detection():
    """Test hàm is_funding_article_llm"""
    print("=== Testing Funding Article Detection ===")
    
    # Test case với bài viết rõ ràng về funding
    funding_article = """
    A startup founded by 21-year-old MIT dropouts has raised $32 million in a Series A funding round.
    The company, which focuses on AI technology, received the investment led by Insight Partners.
    The funding will be used to expand the team and develop new products.
    The valuation of the company is now $300 million.
    """
    
    print("Testing funding article detection...")
    result = is_funding_article_llm(funding_article)
    print(f"Result: {result}")
    
    # Test case với bài viết không phải funding
    non_funding_article = """
    OpenAI has agreed to pay Oracle $30 billion a year for data center services.
    This is a partnership agreement between the two companies.
    The deal will help OpenAI expand its infrastructure.
    """
    
    print("\nTesting non-funding article detection...")
    result = is_funding_article_llm(non_funding_article)
    print(f"Result: {result}")

def main():
    """Run funding detection tests"""
    print("🧪 Testing funding detection...\n")
    
    test_funding_keywords()
    test_funding_article_detection()
    
    print("🎉 Funding detection tests completed!")

if __name__ == "__main__":
    main() 