#!/usr/bin/env python3
"""
Test script để kiểm tra LLM call và tìm warning
"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.llm_utils import llm_prompt
from backend.utils.logger import logger

def test_llm_call():
    """Test LLM call để xem có warning không"""
    print("=== Testing LLM Call ===")
    
    try:
        # Test simple LLM call
        prompt = "What is 2+2? Answer with just the number."
        result = llm_prompt(prompt, max_tokens=10)
        
        if result:
            print(f"✅ LLM call successful: {result}")
        else:
            print("❌ LLM call failed")
            
    except Exception as e:
        print(f"❌ LLM call error: {e}")
        import traceback
        traceback.print_exc()

def test_llm_with_retry():
    """Test LLM call với retry mechanism"""
    print("\n=== Testing LLM Call with Retry ===")
    
    try:
        from backend.utils.retry import llm_call_with_retry
        
        prompt = "What is the capital of France? Answer with just the city name."
        result = llm_call_with_retry(prompt, max_tokens=10)
        
        if result:
            print(f"✅ LLM call with retry successful: {result}")
        else:
            print("❌ LLM call with retry failed")
            
    except Exception as e:
        print(f"❌ LLM call with retry error: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Run LLM tests"""
    print("🧪 Testing LLM calls...\n")
    
    test_llm_call()
    test_llm_with_retry()
    
    print("\n🎉 LLM tests completed!")

if __name__ == "__main__":
    main() 