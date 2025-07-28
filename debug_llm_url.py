#!/usr/bin/env python3
"""
Debug script để kiểm tra LLM URL
"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend import config
import openai

def debug_llm_url():
    """Debug LLM URL setting"""
    print("=== Debug LLM URL ===")
    
    print(f"Config LLM_API_URL: {config.LLM_API_URL}")
    print(f"Config OPENAI_API_KEY: {config.OPENAI_API_KEY[:20]}...")
    
    # Set API base
    openai.api_key = config.OPENAI_API_KEY
    openai.api_base = config.LLM_API_URL
    
    print(f"OpenAI API Base: {openai.api_base}")
    print(f"OpenAI API Key: {openai.api_key[:20]}...")
    
    # Test call
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=10
        )
        print("✅ LLM call successful")
        print(f"Response: {response.choices[0].message.content}")
    except Exception as e:
        print(f"❌ LLM call failed: {e}")

if __name__ == "__main__":
    debug_llm_url() 