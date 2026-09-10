# ArenaOS — Everything Requested, Mapped To What's Real

Every repo Danny listed, and where its capabilities actually live in ArenaOS.
No fake claims: what's built is built; what's next is labeled next.

## Built in (v6, this wave)

| Repo | Capability | Where it lives |
|---|---|---|
| anthropics/skills | SKILL.md skill libraries | `arenaos/skills/` — Anthropic-spec loader; `skill_list / skill_use / skill_create / skill_install` tools; 5 seeded skills |
| anbeime/skill | skill reuse/creation | `skill_create` — the agent writes its own playbooks; `skill_install` clones any git repo of skills |
| gpt-researcher | plan-and-solve research agent | `deep-research` skill: plan → parallel searches → read sources → cross-check → cited report |
| Z4nzu/hackingtool | pentest toolkit workflows | `recon` skill: passive OSINT → enumeration → web mapping → operator-grade report (on authorized targets) |
| DedSecInside/TorBot | onion crawling, link trees | `onion-crawl` skill + `ARENA_TOR_PROXY` routing: the whole browser + http tools exit through Tor when set |
| CloakBrowser | low-detection browsing | Persistent Chromium profile with `--disable-blink-features=AutomationControlled`, persistent cookies, human-like live-login overlay |
| freqtrade | trading research | `trade-research` skill: real market data via http, computed stats (fees/slippage/drawdown), honest risk framing |
| Obsidian-style vault | knowledge graph | `note_write / note_read / note_search` — plain .md + `[[wikilinks]]`, opens directly in Obsidian |
| hermes-agent / wallbreaker / akto / openclaw (own forks) | autonomous multi-agent execution | `agent_spawn` — nested real agent loops with depth cap; uncensored persona (Akto) doing everything with one model |
| OmniRoute | AI gateway | **deliberately excluded** — Danny's rule: ONE model (arena.ai) does everything. No provider routing. |

Also in this wave:
- **Login-freeze bug fixed**: 5s DB connect timeout + pool recycle (a dead
  Render DB fails fast instead of spinning the login forever), 25s hard
  timeout on every frontend request.
- **Keyboard never detaches**: the app shell height follows `visualViewport`
  exactly — the composer stays glued above the keyboard; scrolling can never
  move it (iOS Safari/PWA included).
- **Rebrand**: no Grok/Gemini/ChatGPT names anywhere in the UI.
- **Threat shield (protection, not refusals)**: prompt-injection + exposed-secret
  detection on tool outputs (surfaced as `[THREAT-SHIELD]` warnings, never
  blocks), brute-force monitor on login. The agent itself stays uncensored.
- **Tor**: `ARENA_TOR_PROXY=socks5://127.0.0.1:9050` routes the browser and
  http tools through Tor.

## Next waves (real work, not vaporware)

1. **Render free-tier memory**: Chromium + app in 512MB is tight — a $7
   instance (or `web` transport with lazy launch disabled) is the safe path
   for live arena.ai sessions; skills/vault/tools all run free-tier.
2. **freqtrade deep integration**: running live strategy backtests as a tool
   (requires the freqtrade package installed in the image).
3. **Onion link-tree persistence**: crawl graphs saved to the vault as notes.
4. **Persona configurability**: Akto's name/personality editable in Settings.
