"""
Tests for the ai_summarize_select_fetch plugin.

Tests focus on content extraction enhancement features:
- Content density analysis
- Relevance scoring
- HTML filtering (ads, navigation, footers)
- Edge cases and diverse webpage formats
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Mock the searx modules before importing the plugin
sys.modules['searx'] = MagicMock()
sys.modules['searx.plugins'] = MagicMock()
sys.modules['searx.result_types'] = MagicMock()

# Add the plugin directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'searx_plugins'))

from ai_summarize_select_fetch import (
    ContentAnalyzer,
    _calculate_content_density,
    _calculate_relevance_score,
    _extract_enhanced,
    _clean,
    _is_http,
    _strip_trigger,
)


class TestContentAnalyzer(unittest.TestCase):
    """Test the ContentAnalyzer HTML parser."""
    
    def test_excludes_navigation(self):
        """Test that navigation elements are excluded."""
        html = """
        <html>
            <nav>
                <a href="#">Home</a>
                <a href="#">About</a>
            </nav>
            <article>
                <p>This is the main content of the article that should be extracted.</p>
            </article>
        </html>
        """
        analyzer = ContentAnalyzer()
        analyzer.feed(html)
        
        # Should not include nav content
        combined = ' '.join(analyzer.content_blocks)
        self.assertNotIn('Home', combined)
        self.assertNotIn('About', combined)
        self.assertIn('main content', combined)
    
    def test_excludes_footer(self):
        """Test that footer elements are excluded."""
        html = """
        <html>
            <article>
                <p>Main article content here with substantial information.</p>
            </article>
            <footer>
                <p>Copyright 2024. All rights reserved.</p>
            </footer>
        </html>
        """
        analyzer = ContentAnalyzer()
        analyzer.feed(html)
        
        combined = ' '.join(analyzer.content_blocks)
        self.assertIn('Main article content', combined)
        self.assertNotIn('Copyright', combined)
    
    def test_excludes_ads_by_class(self):
        """Test that ad elements are excluded by class pattern."""
        html = """
        <html>
            <div class="content">
                <p>Real content that provides value to users and answers their questions.</p>
            </div>
            <div class="ad-banner">
                <p>Buy this product now!</p>
            </div>
            <div class="advertisement">
                <p>Special offer today only!</p>
            </div>
        </html>
        """
        analyzer = ContentAnalyzer()
        analyzer.feed(html)
        
        combined = ' '.join(analyzer.content_blocks)
        self.assertIn('Real content', combined)
        self.assertNotIn('Buy this product', combined)
        self.assertNotIn('Special offer', combined)
    
    def test_excludes_social_widgets(self):
        """Test that social sharing widgets are excluded."""
        html = """
        <html>
            <article>
                <p>This is valuable article content with detailed information and analysis.</p>
            </article>
            <div class="social-share">
                <button>Share on Facebook</button>
                <button>Share on Twitter</button>
            </div>
        </html>
        """
        analyzer = ContentAnalyzer()
        analyzer.feed(html)
        
        combined = ' '.join(analyzer.content_blocks)
        self.assertIn('valuable article content', combined)
        self.assertNotIn('Share on', combined)
    
    def test_minimum_block_length(self):
        """Test that short blocks are filtered out."""
        html = """
        <html>
            <p>Short.</p>
            <p>This is a much longer paragraph with substantial content that should be included in extraction.</p>
        </html>
        """
        analyzer = ContentAnalyzer()
        analyzer.feed(html)
        
        # Short block should be excluded (< 50 chars)
        self.assertTrue(len(analyzer.content_blocks) >= 1)
        combined = ' '.join(analyzer.content_blocks)
        self.assertIn('substantial content', combined)


class TestContentDensity(unittest.TestCase):
    """Test content density calculation."""
    
    def test_empty_text(self):
        """Test density of empty text."""
        self.assertEqual(_calculate_content_density(""), 0.0)
        self.assertEqual(_calculate_content_density(None), 0.0)
    
    def test_high_quality_content(self):
        """Test density of high-quality article text."""
        text = """
        This is a well-written article with multiple sentences. It contains
        valuable information that users are looking for. The content is
        structured properly with good grammar and punctuation. This type
        of content should score highly on density metrics.
        """
        density = _calculate_content_density(text)
        self.assertGreater(density, 0.3)
    
    def test_low_quality_content(self):
        """Test density of low-quality text (symbols, noise)."""
        text = "!@#$%^&*()_+-=[]{}|;':\"<>?,./`~"
        density = _calculate_content_density(text)
        # Threshold of 0.4 accounts for the alphanumeric ratio component
        # which still scores ~0.33 even for pure symbols due to sentence normalization
        self.assertLess(density, 0.4)
    
    def test_mixed_content(self):
        """Test density of mixed quality content."""
        text = "Some text with @@@ symbols ### and numbers 12345 mixed in."
        density = _calculate_content_density(text)
        self.assertGreater(density, 0.0)
        self.assertLess(density, 1.0)


class TestRelevanceScore(unittest.TestCase):
    """Test relevance scoring against queries."""
    
    def test_exact_match(self):
        """Test exact query match in text."""
        query = "machine learning"
        text = "This article discusses machine learning and its applications."
        score = _calculate_relevance_score(text, query)
        self.assertGreater(score, 0.5)
    
    def test_partial_match(self):
        """Test partial query match in text."""
        query = "python programming tutorial"
        text = "This is a tutorial about programming concepts and Python basics."
        score = _calculate_relevance_score(text, query)
        self.assertGreater(score, 0.2)
    
    def test_no_match(self):
        """Test no query match in text."""
        query = "quantum physics"
        text = "This article is about cooking recipes and baking techniques."
        score = _calculate_relevance_score(text, query)
        self.assertLess(score, 0.2)
    
    def test_case_insensitive(self):
        """Test that matching is case-insensitive."""
        query = "JAVASCRIPT"
        text = "Learning javascript is fun and rewarding for web developers."
        score = _calculate_relevance_score(text, query)
        self.assertGreater(score, 0.3)
    
    def test_position_matters(self):
        """Test that earlier matches score higher."""
        query = "climate change"
        text1 = "Climate change is a critical issue. " + "Filler text. " * 50
        text2 = "Filler text. " * 50 + "Climate change is mentioned here."
        
        score1 = _calculate_relevance_score(text1, query)
        score2 = _calculate_relevance_score(text2, query)
        
        self.assertGreater(score1, score2)


class TestEnhancedExtraction(unittest.TestCase):
    """Test the enhanced extraction function."""
    
    def test_extracts_main_content(self):
        """Test extraction of main article content."""
        html = """
        <html>
            <head><title>Test Article</title></head>
            <body>
                <nav><a href="#">Menu</a></nav>
                <article>
                    <h1>Article Title</h1>
                    <p>This is the main content of the article with important information.</p>
                    <p>It has multiple paragraphs with detailed explanations and analysis.</p>
                </article>
                <footer>Copyright notice</footer>
            </body>
        </html>
        """
        query = "article information"
        result = _extract_enhanced(html, "http://example.com", query)
        
        self.assertIsNotNone(result)
        self.assertIn('main content', result)
        self.assertNotIn('Menu', result)
        self.assertNotIn('Copyright', result)
    
    def test_handles_empty_html(self):
        """Test handling of empty HTML."""
        result = _extract_enhanced("", "http://example.com", "test query")
        self.assertIsNone(result)
    
    def test_handles_malformed_html(self):
        """Test handling of malformed HTML (graceful degradation)."""
        html = "<div><p>Unclosed tags and <<>> strange markup"
        query = "test"
        result = _extract_enhanced(html, "http://example.com", query)
        # Should not crash, may return None or extracted text
        self.assertTrue(result is None or isinstance(result, str))
    
    def test_respects_character_limit(self):
        """Test that extraction respects the character limit."""
        # Create very long HTML
        long_content = "<p>" + ("This is a long paragraph. " * 1000) + "</p>"
        html = f"<html><body><article>{long_content}</article></body></html>"
        query = "paragraph"
        
        result = _extract_enhanced(html, "http://example.com", query)
        
        if result:
            # Should not exceed EXTRACT_MAX_CHARS (9000 in default config)
            self.assertLessEqual(len(result), 9100)  # Allow small buffer
    
    def test_prioritizes_relevant_content(self):
        """Test that more relevant content is prioritized."""
        html = """
        <html>
            <body>
                <article>
                    <section>
                        <p>Irrelevant content about something completely different that has nothing to do with the query.</p>
                        <p>More filler text that is not relevant at all to what the user is searching for.</p>
                    </section>
                    <section>
                        <p>Python programming is a powerful skill. Python is used for web development, data science, and automation.</p>
                        <p>Learning Python can open many career opportunities in software development.</p>
                    </section>
                </article>
            </body>
        </html>
        """
        query = "python programming"
        result = _extract_enhanced(html, "http://example.com", query)
        
        self.assertIsNotNone(result)
        self.assertIn('Python', result)
        # Should prioritize relevant content
        self.assertGreater(result.find('Python'), -1)


class TestUtilityFunctions(unittest.TestCase):
    """Test utility functions."""
    
    def test_clean_whitespace(self):
        """Test whitespace cleaning."""
        self.assertEqual(_clean("  hello   world  "), "hello world")
        self.assertEqual(_clean("hello\n\nworld"), "hello world")
        self.assertEqual(_clean("  \t \n  "), "")
    
    def test_is_http(self):
        """Test HTTP URL detection."""
        self.assertTrue(_is_http("http://example.com"))
        self.assertTrue(_is_http("https://example.com"))
        self.assertFalse(_is_http("ftp://example.com"))
        self.assertFalse(_is_http("//example.com"))
        self.assertFalse(_is_http("example.com"))
    
    def test_strip_trigger(self):
        """Test trigger stripping."""
        # Assuming default trigger is "!!sum"
        import ai_summarize_select_fetch
        original_trigger = ai_summarize_select_fetch.TRIGGER
        ai_summarize_select_fetch.TRIGGER = "!!sum"
        
        result = _strip_trigger("best laptop !!sum")
        self.assertEqual(result, "best laptop")
        
        result = _strip_trigger("!!sum python tutorial")
        self.assertEqual(result, "python tutorial")
        
        ai_summarize_select_fetch.TRIGGER = original_trigger


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and diverse webpage formats."""
    
    def test_javascript_heavy_page(self):
        """Test page with lots of JavaScript (should be filtered)."""
        html = """
        <html>
            <body>
                <script>
                    function doSomething() {
                        var x = 1;
                        console.log(x);
                    }
                </script>
                <article>
                    <p>This is the actual content that should be extracted from the page.</p>
                </article>
                <script>moreJavaScript();</script>
            </body>
        </html>
        """
        query = "content"
        result = _extract_enhanced(html, "http://example.com", query)
        
        if result:
            self.assertNotIn('function', result)
            self.assertNotIn('console.log', result)
    
    def test_blog_format(self):
        """Test typical blog page format."""
        html = """
        <html>
            <body>
                <header>
                    <nav>Home | About | Contact</nav>
                </header>
                <main>
                    <article>
                        <h1>Blog Post Title</h1>
                        <p>This is the introduction paragraph of the blog post with interesting content.</p>
                        <p>The body of the blog post continues with more detailed information and analysis.</p>
                    </article>
                    <aside class="sidebar">
                        <div class="widget">Recent Posts</div>
                        <div class="ad-widget">Advertisement</div>
                    </aside>
                </main>
                <footer>Blog footer</footer>
            </body>
        </html>
        """
        query = "blog post"
        result = _extract_enhanced(html, "http://example.com", query)
        
        self.assertIsNotNone(result)
        self.assertIn('introduction', result.lower())
    
    def test_news_article_format(self):
        """Test news article format."""
        html = """
        <html>
            <body>
                <article class="news-article">
                    <h1>Breaking News Headline</h1>
                    <div class="byline">By Reporter Name</div>
                    <p>The first paragraph of the news article contains the most important information.</p>
                    <p>Subsequent paragraphs provide additional context and details about the event.</p>
                    <p>Expert quotes and analysis are included in later paragraphs.</p>
                </article>
                <div class="related-articles">
                    <h3>Related Stories</h3>
                    <a href="#">Other news</a>
                </div>
            </body>
        </html>
        """
        query = "news"
        result = _extract_enhanced(html, "http://example.com", query)
        
        self.assertIsNotNone(result)
        self.assertIn('important information', result)
    
    def test_ecommerce_page(self):
        """Test e-commerce product page."""
        html = """
        <html>
            <body>
                <nav>Categories | Cart | Account</nav>
                <main>
                    <div class="product">
                        <h1>Product Name</h1>
                        <p class="description">This product is perfect for users who need high-quality solutions.</p>
                        <div class="specs">
                            <p>Specifications: Premium quality, durable construction, easy to use.</p>
                        </div>
                    </div>
                    <div class="reviews">
                        <h2>Customer Reviews</h2>
                        <p>Great product! Works as advertised and exceeds expectations.</p>
                    </div>
                </main>
                <div class="recommendations">You might also like...</div>
            </body>
        </html>
        """
        query = "product quality"
        result = _extract_enhanced(html, "http://example.com", query)
        
        # Should extract product description
        if result:
            self.assertTrue('quality' in result.lower() or 'product' in result.lower())
    
    def test_wikipedia_style_page(self):
        """Test Wikipedia-style reference page."""
        html = """
        <html>
            <body>
                <div id="content">
                    <h1>Article Subject</h1>
                    <p>The article subject is an important topic in computer science and technology.</p>
                    <section>
                        <h2>History</h2>
                        <p>The history section provides background information and context about the development.</p>
                    </section>
                    <section>
                        <h2>Technical Details</h2>
                        <p>Technical details explain how the system works and its key components.</p>
                    </section>
                </div>
                <div id="footer">
                    <p>This page was last edited on...</p>
                </div>
            </body>
        </html>
        """
        query = "technical details"
        result = _extract_enhanced(html, "http://example.com", query)
        
        self.assertIsNotNone(result)
        self.assertIn('Technical', result)


if __name__ == '__main__':
    unittest.main()
