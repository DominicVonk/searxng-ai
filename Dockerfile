FROM searxng/searxng:latest

USER root

# Needed for fetching + extraction
RUN pip install --no-cache-dir httpx trafilatura

# Copy plugin into searx plugin path inside the image
COPY searx_plugins/ai_summarize_select_fetch.py /usr/local/searxng/searx/plugins/ai_summarize_select_fetch.py

# Copy settings (Coolify can also mount instead; this is simplest)
COPY settings.yml /etc/searxng/settings.yml

USER searxng
