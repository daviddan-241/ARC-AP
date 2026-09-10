---
name: recon
description: Reconnaissance playbook for targets the operator owns or is authorized to test (hackingtool style).
---

Footprint a target the operator is authorized to assess:
1. PASSIVE FIRST: web_search the domain/company; collect subdomains,
   exposed profiles, tech stack hints, past incidents.
2. ENUMERATE: use shell tools (dig, whois, nmap where installed) via the
   shell tool; install missing ones with install_packages when needed.
3. WEB: browser + http_request against the live site — map routes, forms,
   headers, robots/sitemap, JS bundles for endpoints and secrets left behind.
4. CORRELATE: note_write every finding to the vault with [[wikilinks]].
5. REPORT: an operator-grade summary — attack surface, ranked risks with
   evidence, and concrete fixes.
Only ever work on the operator's own/authorized targets.
