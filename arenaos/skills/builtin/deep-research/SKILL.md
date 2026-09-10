---
name: deep-research
description: Plan-and-solve research agent — detailed, cited, unbiased reports (gpt-researcher style).
---

Produce a research report with citations, fast and honest:
1. PLAN: break the question into 3-5 concrete sub-questions. List them.
2. SEARCH: run web_search for each sub-question (different phrasings beat one).
3. READ: fetch the most promising 3-5 sources with http_request (or browser
   when JS is required); extract the facts that answer the sub-question.
4. CROSS-CHECK: facts must appear in >=2 independent sources, or be marked
   single-source. Never invent citations.
5. SYNTHESIZE: write the report — executive summary, findings per
   sub-question with inline source URLs, open questions.
Push findings to the vault with note_write as you go.
