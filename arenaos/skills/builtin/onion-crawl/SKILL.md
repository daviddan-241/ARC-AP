---
name: onion-crawl
description: Tor onion crawling — map .onion sites, titles, descriptions, link trees (TorBot style).
---

Crawl onion sites when Tor routing is enabled:
1. Verify tor routing first: http_request https://check.torproject.org —
   the page must confirm the exit node is Tor. If not, tell the operator
   to enable ARENA_TOR_PROXY (a local Tor SOCKS port, e.g. 9050).
2. browser to the .onion URL; extract title + visible description.
3. list_clickable to harvest links; record the link tree.
4. Save the tree as JSON via write_file, and note_write a summary.
5. Crawl politely: pause between pages; never hammer a hidden service.
Titles over hosts when available; log dead links, don't retry forever.
