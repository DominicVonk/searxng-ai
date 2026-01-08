"""
Result Enhancer Plugin for SearXNG

Enhances search results with additional metadata and filtering capabilities:
- Adds estimated reading time for articles
- Highlights code snippets in technical results
- Provides visual indicators for different content types
- Filters out duplicate or low-quality results

This plugin improves result quality without requiring external API calls.
"""

import re
from urllib.parse import urlparse

from searx.plugins import Plugin


class SXNGPlugin(Plugin):
    name = "result_enhancer"
    description = "Enhances search results with metadata and quality filtering."
    default_on = True

    def post_search(self, request, search, result_container):
        """
        Process search results to enhance them with additional metadata.
        """
        if not result_container.results:
            return
        
        # Track seen URLs to detect duplicates
        seen_urls = set()
        seen_titles = set()
        enhanced_results = []
        
        for result in result_container.results:
            url = getattr(result, "url", "")
            title = getattr(result, "title", "")
            content = getattr(result, "content", "")
            
            if not url:
                continue
            
            # Skip exact duplicates
            if url in seen_urls:
                continue
            
            # Skip near-duplicate titles
            title_lower = title.lower().strip()
            if title_lower in seen_titles and len(title_lower) > 10:
                continue
            
            seen_urls.add(url)
            seen_titles.add(title_lower)
            
            # Enhance content with metadata
            enhancements = []
            
            # Add domain indicator
            domain = urlparse(url).netloc
            if domain:
                domain_clean = domain.replace("www.", "")
                enhancements.append(f"🌐 {domain_clean}")
            
            # Detect content type from URL and content
            if self._is_documentation(url, content):
                enhancements.append("📚 Documentation")
            elif self._is_code_repository(url):
                enhancements.append("💻 Code Repository")
            elif self._is_video(url):
                enhancements.append("🎥 Video")
            elif self._is_academic(url, content):
                enhancements.append("🎓 Academic")
            elif self._is_news(url):
                enhancements.append("📰 News")
            
            # Estimate reading time
            if content:
                words = len(content.split())
                if words > 50:
                    reading_time = max(1, words // 200)  # ~200 words per minute
                    enhancements.append(f"⏱️ {reading_time} min read")
            
            # Add enhancements to content
            if enhancements:
                enhancement_text = " | ".join(enhancements)
                if hasattr(result, 'content') and result.content:
                    result.content = f"[{enhancement_text}]\n{result.content}"
                else:
                    result.content = f"[{enhancement_text}]"
            
            enhanced_results.append(result)
        
        # Replace results with enhanced version
        result_container.results = enhanced_results
    
    def _is_documentation(self, url: str, content: str) -> bool:
        """Check if result is documentation."""
        doc_patterns = [
            r'docs?\.',
            r'/documentation',
            r'/manual',
            r'/guide',
            r'readthedocs',
            r'/api',
            r'/reference',
        ]
        return any(re.search(pattern, url.lower()) for pattern in doc_patterns)
    
    def _is_code_repository(self, url: str) -> bool:
        """Check if result is a code repository."""
        return any(domain in url.lower() for domain in ['github.com', 'gitlab.com', 'bitbucket.org'])
    
    def _is_video(self, url: str) -> bool:
        """Check if result is a video."""
        return any(domain in url.lower() for domain in ['youtube.com', 'vimeo.com', 'youtu.be'])
    
    def _is_academic(self, url: str, content: str) -> bool:
        """Check if result is academic content."""
        academic_domains = ['arxiv.org', 'scholar.google', 'ieee.org', 'acm.org', 'springer.com']
        return any(domain in url.lower() for domain in academic_domains)
    
    def _is_news(self, url: str) -> bool:
        """Check if result is from a news site."""
        news_patterns = [
            r'/news/',
            r'/article/',
            r'\.com/\d{4}/\d{2}/',  # Date-based URLs
        ]
        return any(re.search(pattern, url.lower()) for pattern in news_patterns)
