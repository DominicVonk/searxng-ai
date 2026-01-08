"""
Tests for additional SearXNG plugins:
- ai_quick_answer
- result_enhancer
- smart_suggestions
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Mock the searx modules before importing plugins
sys.modules['searx'] = MagicMock()
sys.modules['searx.plugins'] = MagicMock()
sys.modules['searx.result_types'] = MagicMock()

# Create a real Plugin base class for testing
class MockPlugin:
    def __init__(self):
        pass

sys.modules['searx'].plugins.Plugin = MockPlugin
sys.modules['searx'].result_types.Answer = Mock
sys.modules['searx'].result_types.Suggestion = Mock

# Add the plugin directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'searx_plugins'))

# Now import the actual plugins
import result_enhancer
import smart_suggestions
import ai_quick_answer


class TestResultEnhancer(unittest.TestCase):
    """Test the Result Enhancer plugin."""
    
    def setUp(self):
        """Create plugin instance for each test."""
        self.plugin = result_enhancer.SXNGPlugin()
    
    def test_detects_documentation(self):
        """Test documentation detection."""
        self.assertTrue(self.plugin._is_documentation("https://docs.python.org/3/", ""))
        self.assertTrue(self.plugin._is_documentation("https://readthedocs.io/project/", ""))
        self.assertFalse(self.plugin._is_documentation("https://example.com", ""))
    
    def test_detects_code_repository(self):
        """Test code repository detection."""
        self.assertTrue(self.plugin._is_code_repository("https://github.com/user/repo"))
        self.assertTrue(self.plugin._is_code_repository("https://gitlab.com/user/repo"))
        self.assertFalse(self.plugin._is_code_repository("https://example.com"))
    
    def test_detects_video(self):
        """Test video content detection."""
        self.assertTrue(self.plugin._is_video("https://youtube.com/watch?v=123"))
        self.assertTrue(self.plugin._is_video("https://youtu.be/123"))
        self.assertFalse(self.plugin._is_video("https://example.com"))
    
    def test_detects_academic(self):
        """Test academic content detection."""
        self.assertTrue(self.plugin._is_academic("https://arxiv.org/abs/1234", ""))
        self.assertTrue(self.plugin._is_academic("https://scholar.google.com/", ""))
        self.assertFalse(self.plugin._is_academic("https://example.com", ""))
    
    def test_enhances_results(self):
        """Test that results are enhanced with metadata."""
        # Create mock result container
        result_container = Mock()
        result1 = Mock()
        result1.url = "https://docs.python.org/3/"
        result1.title = "Python Documentation"
        result1.content = "This is a guide to Python programming. " * 50  # Long content
        
        result_container.results = [result1]
        
        # Mock request and search
        request = Mock()
        search = Mock()
        search.search_query.query = "python tutorial"
        
        # Process results
        self.plugin.post_search(request, search, result_container)
        
        # Check that content was enhanced
        self.assertIn("📚 Documentation", result1.content)
        self.assertIn("docs.python.org", result1.content)
        self.assertIn("min read", result1.content)
    
    def test_removes_duplicates(self):
        """Test that duplicate results are filtered."""
        result_container = Mock()
        
        # Create duplicate results
        result1 = Mock()
        result1.url = "https://example.com/page"
        result1.title = "Example Page"
        result1.content = "Content here"
        
        result2 = Mock()
        result2.url = "https://example.com/page"  # Duplicate URL
        result2.title = "Example Page"
        result2.content = "More content"
        
        result_container.results = [result1, result2]
        
        request = Mock()
        search = Mock()
        search.search_query.query = "test"
        
        self.plugin.post_search(request, search, result_container)
        
        # Should only have 1 result after deduplication
        self.assertEqual(len(result_container.results), 1)


class TestSmartSuggestions(unittest.TestCase):
    """Test the Smart Suggestions plugin."""
    
    def setUp(self):
        """Create plugin instance for each test."""
        self.plugin = smart_suggestions.SXNGPlugin()
    
    def test_generates_refinements_for_how_to(self):
        """Test that 'how to' queries get refinement suggestions."""
        result_container = Mock()
        result_container.results = []
        result_container.suggestions = set()
        
        request = Mock()
        search = Mock()
        search.search_query.query = "how to learn python"
        
        self.plugin.post_search(request, search, result_container)
        
        # Should have suggestions
        self.assertGreater(len(result_container.suggestions), 0)
    
    def test_generates_technical_suggestions(self):
        """Test technical query enhancements."""
        result_container = Mock()
        result_container.results = []
        result_container.suggestions = set()
        
        request = Mock()
        search = Mock()
        search.search_query.query = "python web framework"
        
        self.plugin.post_search(request, search, result_container)
        
        # Should suggest tutorial, documentation, or examples
        suggestions_str = str(result_container.suggestions)
        has_tech_suggestion = any(word in suggestions_str.lower() 
                                   for word in ['tutorial', 'documentation', 'example'])
        self.assertTrue(has_tech_suggestion)
    
    def test_extracts_common_terms_from_results(self):
        """Test extraction of common terms from result titles."""
        result_container = Mock()
        
        # Create results with common terms
        result1 = Mock()
        result1.title = "Django Web Framework Tutorial"
        result2 = Mock()
        result2.title = "Django REST Framework Guide"
        result3 = Mock()
        result3.title = "Django Database Models"
        
        result_container.results = [result1, result2, result3]
        result_container.suggestions = set()
        
        request = Mock()
        search = Mock()
        search.search_query.query = "python web"
        
        self.plugin.post_search(request, search, result_container)
        
        # Should extract "django" or "framework" as common terms
        suggestions_str = str(result_container.suggestions).lower()
        self.assertTrue('django' in suggestions_str or 'framework' in suggestions_str)
    
    def test_limits_suggestions(self):
        """Test that suggestions are limited to a reasonable number."""
        result_container = Mock()
        result_container.results = []
        result_container.suggestions = set()
        
        request = Mock()
        search = Mock()
        search.search_query.query = "best programming language"
        
        self.plugin.post_search(request, search, result_container)
        
        # Should not have too many suggestions
        self.assertLessEqual(len(result_container.suggestions), 6)
    
    def test_ignores_short_queries(self):
        """Test that very short queries don't generate suggestions."""
        result_container = Mock()
        result_container.results = []
        result_container.suggestions = set()
        
        request = Mock()
        search = Mock()
        search.search_query.query = "py"
        
        self.plugin.post_search(request, search, result_container)
        
        # Should not generate suggestions for very short queries
        self.assertEqual(len(result_container.suggestions), 0)


class TestAIQuickAnswer(unittest.TestCase):
    """Test the AI Quick Answer plugin."""
    
    def setUp(self):
        """Create plugin instance for each test."""
        self.plugin = ai_quick_answer.SXNGPlugin()
    
    def test_trigger_detection(self):
        """Test that trigger is correctly detected."""
        result_container = Mock()
        result_container.answers = []
        
        request = Mock()
        search = Mock()
        
        # Without trigger
        search.search_query.query = "what is python"
        self.plugin.post_search(request, search, result_container)
        self.assertEqual(len(result_container.answers), 0)
    
    def test_strips_trigger_correctly(self):
        """Test trigger stripping."""
        query = "what is machine learning !!ask"
        clean = ai_quick_answer._strip_trigger(query)
        self.assertEqual(clean, "what is machine learning")
        self.assertNotIn("!!ask", clean)
    
    @patch.object(ai_quick_answer, 'OPENAI_API_KEY', 'test-key')
    @patch.object(ai_quick_answer, '_get_quick_answer')
    def test_generates_answer_with_trigger(self, mock_get_answer):
        """Test that answer is generated when trigger is present."""
        mock_get_answer.return_value = "Python is a programming language."
        
        result_container = Mock()
        result_container.answers = []
        
        request = Mock()
        search = Mock()
        search.search_query.query = "what is python !!ask"
        
        self.plugin.post_search(request, search, result_container)
        
        # Should have called the answer generator
        mock_get_answer.assert_called_once()
    
    def test_no_answer_without_api_key(self):
        """Test that no answer is generated without API key."""
        # Save original key
        original_key = ai_quick_answer.OPENAI_API_KEY
        
        # Temporarily clear API key
        ai_quick_answer.OPENAI_API_KEY = ""
        
        result_container = Mock()
        result_container.answers = []
        
        request = Mock()
        search = Mock()
        search.search_query.query = "what is python !!ask"
        
        self.plugin.post_search(request, search, result_container)
        
        # Should not have added any answers
        self.assertEqual(len(result_container.answers), 0)
        
        # Restore original key
        ai_quick_answer.OPENAI_API_KEY = original_key


if __name__ == '__main__':
    unittest.main()
