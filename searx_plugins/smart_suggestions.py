"""
Smart Suggestions Plugin for SearXNG

Provides intelligent search suggestions based on:
- Query patterns and common searches
- Related topics and refinements
- Spelling corrections
- Alternative phrasings

This plugin helps users find better search terms without external API calls.
"""

import re
from collections import Counter

from searx.plugins import Plugin
from searx.result_types import Suggestion


class SXNGPlugin(Plugin):
    name = "smart_suggestions"
    description = "Provides intelligent search suggestions and refinements."
    default_on = True

    # Common query refinements
    REFINEMENTS = {
        'how to': ['tutorial', 'guide', 'step by step', 'learn'],
        'what is': ['definition', 'explained', 'meaning', 'overview'],
        'best': ['top', 'recommended', 'comparison', 'review'],
        'vs': ['comparison', 'difference between', 'which is better'],
    }
    
    # Technical query enhancers
    TECH_KEYWORDS = {
        'python', 'javascript', 'java', 'rust', 'golang', 'typescript',
        'react', 'vue', 'angular', 'node', 'django', 'flask',
        'docker', 'kubernetes', 'aws', 'azure', 'gcp',
    }
    
    def post_search(self, request, search, result_container):
        """Generate smart suggestions based on the query and results."""
        q = (search.search_query.query or "").strip().lower()
        
        if not q or len(q) < 3:
            return
        
        suggestions = []
        
        # Generate refinement suggestions
        for pattern, refinements in self.REFINEMENTS.items():
            if pattern in q:
                base_query = q.replace(pattern, '').strip()
                for refinement in refinements:
                    if refinement not in q:
                        suggestion = f"{refinement} {base_query}"
                        suggestions.append(suggestion)
        
        # Technical query enhancements
        query_words = set(q.split())
        tech_words = query_words & self.TECH_KEYWORDS
        
        if tech_words:
            for tech in tech_words:
                # Add common technical suffixes
                if 'tutorial' not in q and 'guide' not in q:
                    suggestions.append(f"{q} tutorial")
                if 'documentation' not in q and 'docs' not in q:
                    suggestions.append(f"{q} documentation")
                if 'example' not in q and 'examples' not in q:
                    suggestions.append(f"{q} examples")
        
        # Extract common terms from result titles
        if result_container.results:
            title_words = []
            for result in result_container.results[:10]:
                title = getattr(result, "title", "")
                if title:
                    # Extract meaningful words (length > 3, not in original query)
                    words = re.findall(r'\b\w{4,}\b', title.lower())
                    title_words.extend([w for w in words if w not in query_words])
            
            # Find most common terms not in original query
            if title_words:
                common_terms = Counter(title_words).most_common(5)
                for term, count in common_terms:
                    if count >= 2 and term not in q:
                        suggestions.append(f"{q} {term}")
        
        # Add year for time-sensitive queries
        time_keywords = ['latest', 'current', 'new', 'recent', 'modern', 'updated']
        if any(keyword in q for keyword in time_keywords):
            from datetime import datetime
            current_year = datetime.now().year
            if str(current_year) not in q:
                suggestions.append(f"{q} {current_year}")
        
        # Add "vs alternatives" for product queries
        if 'best' in q or 'top' in q:
            if 'alternative' not in q:
                suggestions.append(f"{q} alternatives")
        
        # Limit to top 5 unique suggestions
        unique_suggestions = []
        seen = set()
        for s in suggestions:
            s_normalized = s.strip().lower()
            if s_normalized not in seen and s_normalized != q:
                unique_suggestions.append(s.title() if not any(tech in s for tech in self.TECH_KEYWORDS) else s)
                seen.add(s_normalized)
                if len(unique_suggestions) >= 5:
                    break
        
        # Add suggestions to result container
        for suggestion_text in unique_suggestions:
            result_container.suggestions.add(suggestion_text)
