FROM searxng/searxng:latest

USER root

# Needed for fetching + extraction
RUN pip install --no-cache-dir httpx trafilatura

# Copy all plugins into searx plugin path inside the image
COPY searx_plugins/ai_summarize_select_fetch.py /usr/local/searxng/searx/plugins/ai_summarize_select_fetch.py
COPY searx_plugins/ai_quick_answer.py /usr/local/searxng/searx/plugins/ai_quick_answer.py
COPY searx_plugins/result_enhancer.py /usr/local/searxng/searx/plugins/result_enhancer.py
COPY searx_plugins/smart_suggestions.py /usr/local/searxng/searx/plugins/smart_suggestions.py

# Copy settings (Coolify can also mount instead; this is simplest)
COPY settings.yml /etc/searxng/settings.yml

USER searxng
