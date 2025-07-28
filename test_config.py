#!/usr/bin/env python3
"""
Test script để kiểm tra config loading
"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend import config

def test_config_loading():
    """Test việc load config"""
    print("=== Testing Config Loading ===")
    
    print(f"OPENAI_API_KEY: {config.OPENAI_API_KEY[:20]}..." if config.OPENAI_API_KEY else "OPENAI_API_KEY: None")
    print(f"TAVILY_API_KEY: {config.TAVILY_API_KEY[:20]}..." if config.TAVILY_API_KEY else "TAVILY_API_KEY: None")
    print(f"LLM_API_URL: {config.LLM_API_URL}")
    print(f"LLM_MODEL_ID: {config.LLM_MODEL_ID}")
    
    # Test if keys are loaded
    if config.OPENAI_API_KEY and config.OPENAI_API_KEY.startswith('sk-proj-'):
        print("✅ OPENAI_API_KEY loaded correctly")
    else:
        print("❌ OPENAI_API_KEY not loaded or invalid")
    
    if config.TAVILY_API_KEY and config.TAVILY_API_KEY.startswith('tvly-'):
        print("✅ TAVILY_API_KEY loaded correctly")
    else:
        print("❌ TAVILY_API_KEY not loaded or invalid")

def test_llm_utils_import():
    """Test import llm_utils"""
    print("\n=== Testing LLM Utils Import ===")
    
    try:
        from backend.llm_utils import llm_prompt
        print("✅ LLM utils imported successfully")
        
        # Test simple LLM call
        print("Testing LLM call...")
        result = llm_prompt("Hello", max_tokens=10)
        if result:
            print("✅ LLM call successful")
        else:
            print("❌ LLM call failed")
            
    except Exception as e:
        print(f"❌ Error importing LLM utils: {e}")

def test_search_utils_import():
    """Test import search_utils"""
    print("\n=== Testing Search Utils Import ===")
    
    try:
        from backend.search_utils import search_tavily
        print("✅ Search utils imported successfully")
        
        # Test simple Tavily call
        print("Testing Tavily call...")
        results = search_tavily("test", max_results=1)
        if results:
            print("✅ Tavily call successful")
        else:
            print("❌ Tavily call failed")
            
    except Exception as e:
        print(f"❌ Error importing search utils: {e}")

def main():
    """Run config tests"""
    print("🧪 Testing configuration...\n")
    
    test_config_loading()
    test_llm_utils_import()
    test_search_utils_import()
    
    print("\n🎉 Config tests completed!")

if __name__ == "__main__":
    main() 