# SearXNG AI

A full, working setup to run SearXNG + an AI LLM summary plugin on Coolify, including:
- Building a custom SearXNG image (so you can ship your plugin + extra Python deps)
- Configuring OpenAI-like API (base URL + key)
- Enabling the plugin in settings.yml
- Having the plugin use all result snippets to choose the best links to fetch, then fetch + extract + summarize

## Repository Layout

```
searxng-ai/
  Dockerfile
  settings.yml
  searx_plugins/
    ai_summarize_select_fetch.py
```

## How It Works

1. **LLM Selection**: When you trigger a search with `!!sum`, the plugin sends all search result snippets to an LLM to intelligently select the most relevant URLs
2. **Content Fetching**: The plugin fetches and extracts clean text from the selected URLs using trafilatura
3. **AI Summary**: The LLM generates a comprehensive summary with:
   - 3-7 factual bullet points
   - Suggested links with explanations
   - Follow-up query suggestions

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

### Required:
```bash
OPENAI_API_KEY=sk-xxxxxxxx
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

### Optional (with defaults):
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

### For OpenAI-compatible gateways (LiteLLM/OpenRouter/etc):
```bash
OPENAI_BASE_URL=https://your-gateway.example.com/v1
OPENAI_API_KEY=whatever-your-gateway-requires
```

## Usage

In the SearXNG search box, add `!!sum` to your query:

```
best home assistant zigbee dongle !!sum
```

You'll get:
- Normal search results
- An AI summary panel with:
  - Key findings in bullet points
  - Suggested links with explanations
  - Follow-up query suggestions

## Production Settings

To keep things fast and stable:
- **Keep it opt-in** (!!sum) - don't LLM every search
- **Keep FETCH_K ~ 5-8** - fetching too many pages slows things down
- **Keep timeouts tight** (4s fetch, 12s summarize)
- **Expect some sites to block bots** - plugin will fall back to snippets

## Architecture

The plugin uses SearXNG's official plugin hooks:
- `post_search` hook to process results after search completes
- Injects an `Answer` into the answer panel (SearXNG "answer result" type)
- Fails gracefully if API key is missing or requests time out

## Technical Details

### Dependencies
- **httpx**: Async HTTP client for fetching pages
- **trafilatura**: Extract clean text from HTML pages
- **requests**: For OpenAI API calls (sync)

### Plugin Logic
1. Check if query contains trigger (default: `!!sum`)
2. Send all result snippets to LLM to select best URLs
3. Fetch and extract content from selected URLs (async, parallel)
4. Send extracted content to LLM for summarization
5. Display summary in SearXNG answer panel

### Security
- Plugin fails closed (doesn't break search if API key missing)
- Limited fetch size (700KB max per page)
- Limited extract size (9000 chars max per page)
- Tight timeouts to prevent hanging
- User agent identification for fetching

## Troubleshooting

**Plugin not appearing**: Check that settings.yml has the plugin enabled and the path matches where it's copied in the Dockerfile.

**No AI summary**: Verify `OPENAI_API_KEY` is set and `!!sum` is in your query.

**Slow responses**: Reduce `SEARXNG_AI_FETCH_K` or tighten timeouts.

**Fetch blocked**: Some sites block bots. Plugin will fall back to search result snippets for summary.

## License

See LICENSE file in this repository.
