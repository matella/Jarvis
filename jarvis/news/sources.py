"""News sources (v1 starter — broad mix). Operator-editable; URLs are config, not contract.

Each source's host must be egress-allowlisted for the fetcher to reach it (the configured list IS
the trust boundary). Tweak freely — add/remove feeds, fix any URL that moved.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class NewsSource:
    name: str
    rss_url: str
    lang: str


SOURCES: list[NewsSource] = [
    # World (English)
    NewsSource("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml", "en"),
    NewsSource("The Guardian World", "https://www.theguardian.com/world/rss", "en"),
    NewsSource("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", "en"),
    NewsSource("NPR News", "https://feeds.npr.org/1001/rss.xml", "en"),
    NewsSource("DW World", "https://rss.dw.com/rdf/rss-en-world", "en"),
    # Belgium / Europe (FR / NL)
    NewsSource("Le Soir", "https://www.lesoir.be/rss", "fr"),
    NewsSource("La Libre", "https://www.lalibre.be/rss", "fr"),
    NewsSource("RTBF Info", "https://www.rtbf.be/rss/info", "fr"),
    NewsSource("VRT NWS", "https://www.vrt.be/vrtnws/nl.rss.articles.xml", "nl"),
    NewsSource("Politico Europe", "https://www.politico.eu/feed/", "en"),
]


def source_hosts() -> set[str]:
    """The hostnames the news fetcher is allowed to reach (for egress allowlisting)."""
    return {(urlsplit(s.rss_url).hostname or "").lower() for s in SOURCES}
