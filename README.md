# SearXNG AI

A full, working setup to run SearXNG with multiple AI-powered and enhancement plugins on Coolify, including:
- Building a custom SearXNG image (so you can ship your plugins + extra Python deps)
- Configuring OpenAI-like API (base URL + key)
- Enabling multiple useful plugins in settings.yml
- AI-powered summarization, quick answers, result enhancement, and smart suggestions

## Included Plugins

### 1. AI Summarize Select Fetch (`!!sum`)
**Requires:** OpenAI API key

The main AI summarization plugin:
- LLM intelligently selects the most relevant URLs from search results
- Fetches and extracts clean content using advanced heuristics
- Generates comprehensive summaries with:
  - 3-7 factual bullet points
  - Suggested links with explanations
  - Follow-up query suggestions

**Usage:** Add `!!sum` to your search query
```
best home assistant zigbee dongle !!sum
```

### 2. AI Quick Answer (`!!ask`)
**Requires:** OpenAI API key

Get instant AI answers for simple queries without fetching external URLs:
- Faster than full summarization (no URL fetching)
- Perfect for definitions, quick facts, simple questions
- Concise answers under 3 paragraphs

**Usage:** Add `!!ask` to your search query
```
what is quantum computing !!ask
```

### 3. Result Enhancer (Always Active)
**No API key needed**

Automatically enhances search results with metadata:
- 🌐 Shows clean domain names
- 📚 Identifies documentation
- 💻 Flags code repositories
- 🎥 Marks video content
- 📰 Highlights news articles
- 🎓 Identifies academic papers
- ⏱️ Estimates reading time

Also filters out duplicate and low-quality results.

### 4. Smart Suggestions (Always Active)
**No API key needed**

Provides intelligent search refinements:
- Query pattern suggestions (e.g., "how to" → "tutorial", "guide")
- Technical query enhancements (adds "tutorial", "documentation", "examples")
- Common terms from result titles
- Time-sensitive suggestions (adds current year for "latest" queries)
- Alternative suggestions for product searches

## Repository Layout

```
searxng-ai/
  Dockerfile
  settings.yml
  searx_plugins/
    ai_summarize_select_fetch.py  # Main AI summarization
    ai_quick_answer.py             # Quick AI answers
    result_enhancer.py             # Result metadata
    smart_suggestions.py           # Smart refinements
  tests/
    test_ai_summarize_select_fetch.py
```

## Deployment on Coolify

### Option A: Dockerfile Build Pack (Recommended)

1. Push this repo to GitHub
2. Coolify → New Resource → Application → pick your repo
3. In Build Pack, choose **Dockerfile**
4. Expose port **8080**
5. Add a domain and enable TLS (normal Coolify routing)

### Option B: Docker Compose Build Pack

If you prefer compose (e.g., to add Redis), create a `docker-compose.yml` and choose Docker Compose build pack in Coolify.

## Environment Variables

Configure these in Coolify → App → Environment Variables (mark `OPENAI_API_KEY` as secret):

### Required (for AI plugins):
```bash
OPENAI_API_KEY=sk-xxxxxxxx
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

### Optional (with defaults):

**AI Summarization Plugin:**
```bash
# Trigger pattern for AI summary
SEARXNG_AI_TRIGGER=!!sum

# LLM selection and fetching limits
SEARXNG_AI_RESULTS_FOR_SELECTION=40  # snippets to consider
SEARXNG_AI_SELECT_K=12               # URLs LLM returns
SEARXNG_AI_FETCH_K=7                 # URLs we actually fetch

# Timeouts and limits
SEARXNG_AI_FETCH_TIMEOUT=4.0
SEARXNG_AI_FETCH_MAX_BYTES=700000
SEARXNG_AI_EXTRACT_MAX_CHARS=9000
SEARXNG_AI_SELECT_TIMEOUT=7.0
SEARXNG_AI_SUMMARIZE_TIMEOUT=12.0

# User agent for fetching
SEARXNG_AI_UA=Mozilla/5.0 (compatible; SearXNG-AI/1.0)
```

**AI Quick Answer Plugin:**
```bash
# Trigger pattern for quick answers
SEARXNG_AI_QUICK_TRIGGER=!!ask

# Timeout for quick answers
SEARXNG_AI_QUICK_TIMEOUT=5.0
```

### For OpenAI-compatible gateways (LiteLLM/OpenRouter/etc):
```bash
OPENAI_BASE_URL=https://your-gateway.example.com/v1
OPENAI_API_KEY=whatever-your-gateway-requires
```

## Usage

### AI Summarization
In the SearXNG search box, add `!!sum` to your query:

```
best home assistant zigbee dongle !!sum
```

You'll get:
- Normal search results (enhanced with metadata)
- An AI summary panel with:
  - Key findings in bullet points
  - Suggested links with explanations
  - Follow-up query suggestions

### Quick AI Answers
For faster answers to simple queries, use `!!ask`:

```
what is machine learning !!ask
how does DNS work !!ask
```

You'll get:
- Normal search results (enhanced with metadata)
- A concise AI answer without fetching URLs
- Smart search suggestions

### Automatic Enhancements
The Result Enhancer and Smart Suggestions plugins work automatically on every search:
- Results show content type icons (📚 docs, 💻 code, 🎥 video, etc.)
- Reading time estimates for articles
- Duplicate results are filtered out
- Related search suggestions appear at the bottom

## Production Settings

To keep things fast and stable:
- **Keep it opt-in** (`!!sum` and `!!ask`) - don't LLM every search
- **Keep FETCH_K ~ 5-8** - fetching too many pages slows things down
- **Keep timeouts tight** (4s fetch, 12s summarize, 5s quick answer)
- **Expect some sites to block bots** - plugin will fall back to snippets
- **Result Enhancer and Smart Suggestions** are lightweight and can stay always-on

## Plugin Details

### AI Plugins Architecture
The AI plugins use SearXNG's official plugin hooks:
- `post_search` hook to process results after search completes
- Inject `Answer` objects into the answer panel (SearXNG "answer result" type)
- Fail gracefully if API key is missing or requests time out

### Result Enhancer
- Runs on every search (minimal overhead)
- Analyzes URLs and content to classify results
- Removes exact duplicates and near-duplicate titles
- Adds visual indicators using emoji icons
- No external dependencies or API calls

### Smart Suggestions
- Analyzes query patterns to suggest refinements
- Extracts common terms from result titles
- Provides technical query enhancements
- Suggests time-sensitive additions (current year)
- No external dependencies or API calls

## Technical Details

### Dependencies
- **httpx**: Async HTTP client for fetching pages (AI summarization)
- **trafilatura**: Extract clean text from HTML pages (AI summarization)
- **requests**: For OpenAI API calls (AI plugins)

### AI Summarization Plugin Logic
1. Check if query contains trigger (default: `!!sum`)
2. Send all result snippets to LLM to select best URLs
3. Fetch and extract content from selected URLs (async, parallel)
4. Use advanced content extraction with:
   - HTML filtering (removes ads, nav, footers)
   - Content density scoring
   - NLP-based relevance ranking
5. Send extracted content to LLM for summarization
6. Display summary in SearXNG answer panel

### AI Quick Answer Plugin Logic
1. Check if query contains trigger (default: `!!ask`)
2. Send query directly to LLM (no URL fetching)
3. Get concise answer with max 500 tokens
4. Display answer in SearXNG answer panel

### Result Enhancer Logic
1. Run on every search automatically
2. Detect and filter duplicate URLs and titles
3. Classify content by analyzing URL patterns
4. Add metadata and visual indicators
5. Estimate reading time from content length

### Smart Suggestions Logic
1. Run on every search automatically
2. Analyze query patterns for refinement opportunities
3. Extract common terms from top result titles
4. Generate related search suggestions
5. Add suggestions to SearXNG suggestion panel

### Security
- All plugins fail closed (don't break search if API key missing)
- AI Summarization: Limited fetch size (700KB max per page)
- AI Summarization: Limited extract size (9000 chars max per page)
- All AI plugins: Tight timeouts to prevent hanging
- User agent identification for fetching
- No plugins execute arbitrary code or make unsafe operations

## Troubleshooting

**Plugins not appearing**: Check that settings.yml has the plugins enabled and the paths match where they're copied in the Dockerfile.

**No AI summary or quick answer**: Verify `OPENAI_API_KEY` is set and the appropriate trigger (`!!sum` or `!!ask`) is in your query.

**Slow responses with !!sum**: Reduce `SEARXNG_AI_FETCH_K` or tighten timeouts.

**Fetch blocked with !!sum**: Some sites block bots. Plugin will fall back to search result snippets for summary.

**Result enhancer not showing metadata**: Check that the plugin is enabled in settings.yml and marked as `active: true`.

**No smart suggestions**: The plugin runs automatically. If you don't see suggestions, it may be that no relevant refinements were found for your query.

## License

See LICENSE file in this repository.
