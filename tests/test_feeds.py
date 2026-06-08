

def test_atom_link_prefers_alternate_over_self() -> None:
    # An Atom entry with a rel=self .rss.xml link first + the real article as rel=alternate.
    from jarvis.connectors.feeds import parse_feed
    xml = b"""<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>Test</title>
        <id>urn:x</id>
        <link href="https://site/article~123.rss.xml"/>
        <link href="https://short.site/p.abc" rel="alternate" title="Test"/>
        <link href="https://img/x.jpg" rel="enclosure" type="image/jpeg"/>
        <summary>body</summary>
      </entry>
    </feed>"""
    items = parse_feed(xml)
    assert items[0].link == "https://short.site/p.abc"
