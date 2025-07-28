#!/usr/bin/env python3
"""
Debug test case 1
"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.llm_utils import has_funding_keywords

def debug_test1():
    """Debug test case 1"""
    
    test_text = "21-year-old MIT dropouts raise $32M at $300M valuation led by Insight"
    text_lower = test_text.lower()
    
    print(f"Testing text: '{test_text}'")
    print(f"Lowercase: '{text_lower}'")
    
    # Check funding keywords
    funding_keywords = [
        # Direct funding terms
        'raises', 'raised', 'funding round', 'investment round', 'series a', 'series b', 'series c',
        'seed round', 'angel round', 'venture round', 'fundraising', 'capital raise',
        'venture capital', 'angel investment', 'angel investor', 'angel funding',
        'backed by', 'invested in', 'led by', 'co-led by', 'participated in',
        'closes funding', 'announces funding', 'secures funding', 'receives investment',
        'funding led by', 'investment led by', 'round led by',
        
        # Additional funding terms
        'funding', 'investment', 'capital', 'financing', 'funding round', 'investment round',
        'series funding', 'seed funding', 'angel funding', 'venture funding',
        'equity funding', 'debt funding', 'convertible note', 'pre-seed funding',
        'growth funding', 'expansion funding', 'strategic investment',
        
        # Amount patterns
        'million in funding', 'billion in funding', 'million investment', 'billion investment',
        'million raised', 'billion raised', 'million funding', 'billion funding',
        'million capital', 'billion capital', 'million financing', 'billion financing',
        
        # Investor patterns
        'investors', 'venture capitalists', 'vc firms', 'angel investors',
        'private equity', 'investment firms', 'fund managers',
        
        # Funding announcement patterns
        'announces', 'announced', 'announcement', 'closes', 'closed', 'closing',
        'secures', 'secured', 'receives', 'received', 'obtains', 'obtained',
        
        # Additional context
        'funding round', 'investment round', 'capital round', 'equity round',
        'pre-seed', 'seed funding', 'series funding', 'growth funding',
        'strategic investment', 'equity investment', 'debt funding', 'convertible note',
        
        # More flexible patterns
        'funding', 'investment', 'capital', 'financing', 'backing', 'support',
        'funded', 'invested', 'backed', 'supported', 'financed'
    ]
    
    print("\nChecking funding keywords:")
    found_keywords = []
    for keyword in funding_keywords:
        if keyword in text_lower:
            found_keywords.append(keyword)
            print(f"  ✅ Found: '{keyword}'")
    
    print(f"\nTotal funding keywords found: {len(found_keywords)}")
    
    # Check false positive indicators
    false_positive_indicators = [
        'competition', 'challenge', 'contest', 'award', 'grant', 'prize',
        'million users', 'billion users', 'million downloads', 'billion downloads',
        'million revenue', 'billion revenue', 'million valuation', 'billion valuation',
        'partnership', 'deal', 'agreement', 'contract', 'service', 'product launch'
    ]
    
    print("\nChecking false positive indicators:")
    found_false_positives = []
    for indicator in false_positive_indicators:
        if indicator in text_lower:
            found_false_positives.append(indicator)
            print(f"  ⚠️  Found: '{indicator}'")
    
    print(f"\nTotal false positive indicators found: {len(found_false_positives)}")
    
    # Check specific funding terms
    specific_funding_terms = [
        'raises', 'raised', 'funding round', 'investment round', 'series a', 'series b', 'series c',
        'seed round', 'angel round', 'venture round', 'fundraising', 'capital raise',
        'venture capital', 'angel investment', 'backed by', 'invested in'
    ]
    
    print("\nChecking specific funding terms:")
    found_specific = []
    for term in specific_funding_terms:
        if term in text_lower:
            found_specific.append(term)
            print(f"  ✅ Found: '{term}'")
    
    print(f"\nTotal specific funding terms found: {len(found_specific)}")
    
    # Check funding context indicators
    funding_context_indicators = [
        'raises', 'raised', 'funding', 'investment', 'venture capital', 'angel investment',
        'series a', 'series b', 'series c', 'seed round', 'angel round'
    ]
    
    print("\nChecking funding context indicators:")
    found_context = []
    for indicator in funding_context_indicators:
        if indicator in text_lower:
            found_context.append(indicator)
            print(f"  ✅ Found: '{indicator}'")
    
    print(f"\nTotal funding context indicators found: {len(found_context)}")
    
    # Check funding related terms
    funding_related_terms = [
        'funding', 'investment', 'capital', 'financing', 'venture capital', 'angel investment',
        'investors', 'venture capitalists', 'vc firms', 'angel investors'
    ]
    
    print("\nChecking funding related terms:")
    found_related = []
    for term in funding_related_terms:
        if term in text_lower:
            found_related.append(term)
            print(f"  ✅ Found: '{term}'")
    
    print(f"\nTotal funding related terms found: {len(found_related)}")
    
    # Final result
    result = has_funding_keywords(test_text)
    print(f"\nFinal result: {result}")

if __name__ == "__main__":
    debug_test1() 