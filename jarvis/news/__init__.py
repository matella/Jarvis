"""News module — scrape → pool/dedup → tier-A summary / tier-B synthesis → present.

The table owns the truth (`news_articles`, `news_stories`); the reactor enriches on the
`news.article_scraped` event. Read by both faces (Jarvis cards/voice + the standalone site).
"""
