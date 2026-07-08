# GITNOVA V3 — FINAL EXECUTION PLAN
### The build bible. Paste this to your AI IDE. Execute ONE task at a time, in order. Do not skip. Do not bundle. Do not redesign mid-build.
### Role for the IDE: Principal AI Engineer + patient teacher. Role for you (Hari): the engineer who must UNDERSTAND every piece to defend it in a 10+ LPA interview.

---

## ⚙️ HOW TO USE THIS PLAN (read once, then follow literally)

This plan is a sequence of TASKS. Each task has:
- **GOAL** — what this task achieves
- **IDE INSTRUCTION** — paste this to the AI IDE
- **DONE WHEN** — the exact condition that means the task is complete
- **UNDERSTAND GATE** — what you must be able to explain before moving on
- **IF IT BREAKS** — the discipline rule

**THE THREE LAWS (never break these):**
1. **One task at a time.** Finish a task fully (DONE WHEN met) before touching the next. Never run two tasks at once.
2. **Fix, don't redesign.** When something breaks, fix THAT bug. Do NOT change the architecture, swap models, or rethink the approach. The design is locked. Bugs are normal; redesign is the trap that got you stuck before.
3. **Understand before advancing.** If you can't explain what a task built in plain English, you are not done — ask the IDE to explain, then move on.

**EXPECTATION SETTING:** The first full pipeline run WILL produce errors. This is normal engineering, not failure. Expect 2-3 fix cycles per phase. Budget for it. Do not interpret a bug as "the project is broken."

---

## 🎯 THE GOAL OF THIS BUILD
Get the V3 RAG pipeline working end-to-end on 3-5 test repos, producing real grounded hints, with ONE real eval number from real merged-PR ground truth. Then scale to 65 repos. The deliverable: a working, instrumented, defensible project + a precision number for interviews.

---

# ═══════════════════════════════════════
# PHASE 0 — ENVIRONMENT SETUP (no code yet)
# ═══════════════════════════════════════

## TASK 0.1 — Wire the new Supabase project
**GOAL:** Connect the codebase to the fresh V3 Supabase project.
**IDE INSTRUCTION:**
```
Update my .env with the new Supabase V3 project credentials. I will provide SUPABASE_URL and SUPABASE_KEY (service_role key). Confirm the .env structure includes: SUPABASE_URL, SUPABASE_KEY, GROQ_API_KEY, NVIDIA_API_KEY, GITHUB_TOKEN. Verify .env is in .gitignore so keys are never committed. Do not write any other code.
```
**DONE WHEN:** `.env` has all 5 keys and is gitignored.
**UNDERSTAND GATE:** You know why we use the service_role key (backend writes) not anon key (read-only/RLS-blocked).
**IF IT BREAKS:** Missing key → get it from Supabase Settings → API, or build.nvidia.com for NVIDIA.

## TASK 0.2 — Apply the V3 schema to the new project
**GOAL:** Create all V3 tables/functions in the empty new Supabase project.
**IDE INSTRUCTION:**
```
Guide me to run my 4 migration files (migrations/01_rag_schema.sql, 02_hybrid_search.sql, 03_alter_issues.sql, 04_activate_snapshot.sql) IN ORDER in the new Supabase project's SQL editor. After I run each, tell me what to verify exists (which tables, which functions). Note: 03_alter_issues.sql expects an 'issues' table — tell me whether I need to create the base issues table first in this new project, and if so give me that CREATE TABLE statement matching my V2 schema (id, title, url, repo_name, difficulty, ai_score, ai_hint, category, status, created_at, updated_at).
```
**DONE WHEN:** New project has: `issues`, `repository_snapshots`, `code_chunks` tables + `match_chunks_vector`, `match_chunks_lexical`, `activate_snapshot` functions.
**UNDERSTAND GATE:** You can explain what `repository_snapshots` (versioned repo index state) and `code_chunks` (the embedded code pieces) store, and why snapshots have a STAGING→ACTIVE lifecycle.
**IF IT BREAKS:** Migration error → read the error, it usually names the missing dependency. Run in the correct order. Likely you need the base `issues` table created first.

## TASK 0.3 — Verify the embedding model loads
**GOAL:** Confirm Jina code-embeddings loads on your machine before relying on it.
**IDE INSTRUCTION:**
```
Write a tiny throwaway script test_embed.py that loads jinaai/jina-embeddings-v2-base-code via sentence-transformers and embeds one test string, printing the vector length. This verifies the model downloads and runs on my machine. After it works, we delete it. Explain expected output (a 768 or 384 dim vector — confirm which dimension this model produces and whether it matches my schema's vector(384)).
```
**DONE WHEN:** Script prints a vector and you've confirmed the dimension MATCHES your schema (`vector(384)`).
**UNDERSTAND GATE:** ⚠️ CRITICAL CHECK — Jina v2 base code outputs 768 dimensions by default, but your schema says `vector(384)`. If there's a mismatch, the IDE must reconcile it NOW (either change schema to 768 or confirm the model is configured for 384). Do not proceed with a dimension mismatch — it will silently break retrieval.
**IF IT BREAKS:** Dimension mismatch → fix the schema OR the model config so they agree. Download fails → check internet/disk space.

---

# ═══════════════════════════════════════
# PHASE 1 — RAG INDEXING (prove code gets indexed)
# ═══════════════════════════════════════

## TASK 1.1 — Index ONE Python repo end-to-end
**GOAL:** Prove the indexer can chunk + embed + store one repo's code.
**IDE INSTRUCTION:**
```
Walk me through running code_indexer.py on ONE repo only: fastapi/fastapi. Before running, explain in plain English the full flow: how it fetches files (github_client + ETag), how it chunks Python via AST, how it embeds chunks, and how it writes to repository_snapshots (STAGING) and code_chunks, then promotes to ACTIVE via activate_snapshot. Then run it. After it runs, tell me the exact SQL queries to run in Supabase to verify: (a) one ACTIVE snapshot exists for fastapi/fastapi, (b) code_chunks has rows with non-null embeddings. Do not index any other repo yet.
```
**DONE WHEN:** Supabase shows 1 ACTIVE snapshot for fastapi/fastapi + code_chunks populated with embeddings.
**UNDERSTAND GATE:** You can explain: what one "chunk" is, why STAGING→ACTIVE exists (atomic swap so a crashed index never corrupts live data), and what `commit_sha` ties a chunk to.
**IF IT BREAKS:** Common: API rate limit (check token), embedding dim mismatch (Phase 0.3), or AST parse error on a file (the generic fallback should catch it — verify it does). Fix the specific error; do not change the chunking design.

## TASK 1.2 — Index one NON-Python repo (test the generic path)
**GOAL:** Prove the sliding-window fallback works for JS/TS repos.
**IDE INSTRUCTION:**
```
Run code_indexer.py on ONE non-Python repo: facebook/react. This exercises the _chunk_generic_code sliding-window path instead of AST. Confirm via SQL that react now has an ACTIVE snapshot and code_chunks rows. Then tell me honestly: did it index .js/.jsx/.ts files, or did it skip them? If it skipped non-Python files entirely, flag it as a real problem and propose the minimal fix to ensure non-Python files ARE chunked and stored.
```
**DONE WHEN:** react has an ACTIVE snapshot with code_chunks, AND you've confirmed non-Python files are actually indexed (not skipped).
**UNDERSTAND GATE:** You can explain the difference between AST chunking (Python, clean function boundaries) and sliding-window chunking (other langs, size-based) — and that this is a known tradeoff you'd improve with tree-sitter later.
**IF IT BREAKS / SKIPS:** If non-Python files are skipped, this is the one real RAG risk we flagged. Fix it minimally so they're indexed. Do not rebuild the whole chunker.

---

# ═══════════════════════════════════════
# PHASE 2 — RAG RETRIEVAL (prove it finds the right code)
# ═══════════════════════════════════════

## TASK 2.1 — Retrieve for a known issue
**GOAL:** Prove retrieval returns relevant chunks for a real issue.
**IDE INSTRUCTION:**
```
Write a small test script that calls retrieve_code_for_issue() for one real fastapi issue (give it a real issue title+body about a known fastapi area). Print the retrieved chunks: file paths, symbols, and rrf_score. Before running, explain how the retrieval works step by step: embed query → match_chunks_vector (top 20) + match_chunks_lexical (top 20) → combine_rrf → dedupe → token budget → format. After running, we judge by eye: do the retrieved files look relevant to the issue? Explain why RRF ranked the top result first.
```
**DONE WHEN:** Retrieval returns chunks, and the top results are plausibly relevant to the issue (eyeball check).
**UNDERSTAND GATE:** You can explain RRF in your own words (rank-based fusion, score = Σ 1/(k+rank), why rank not raw score), and what happens when lexical returns zero (vector carries it).
**IF IT BREAKS:** Empty results → check the snapshot is ACTIVE + commit_sha matches. Irrelevant results → that's a quality observation, note it; do not redesign retrieval, the eval will quantify it later.

---

# ═══════════════════════════════════════
# PHASE 3 — LLM GATEWAY (the main remaining code)
# ═══════════════════════════════════════

## TASK 3.1 — Build the NVIDIA NIM + Groq fallback gateway in bot.py
**GOAL:** Finish bot.py so it tries NVIDIA first, falls back to Groq, and returns which provider/model answered.
**IDE INSTRUCTION:**
```
bot.py is currently staged/incomplete. Implement the multi-provider gateway per my plan, ONE function at a time, explaining each before writing it:
1. An NVIDIA NIM client (OpenAI-compatible, base_url https://integrate.api.nvidia.com/v1, model meta/llama-3.3-70b-instruct, env NVIDIA_API_KEY).
2. An ordered fallback cascade in evaluate_and_enrich: try NVIDIA → on failure/429 try Groq llama-3.3-70b-versatile → then Groq llama-3.1-8b-instant → else return None.
3. The function must RETURN (response_json_str, provider_name, model_name) so the caller can log which provider actually answered.
4. Inject the RAG retrieved_code into build_user_prompt (a new section "--- RETRIEVED SOURCE CODE ---") ONLY when retrieved_code is non-empty; if empty, the prompt is exactly the V2 metadata-only prompt (graceful degrade).
After each function, explain what it does and why. Do not change the existing SYSTEM_PROMPT rules or the validator.
```
**DONE WHEN:** `evaluate_and_enrich` returns `(response, provider, model)`, tries NVIDIA then Groq, and injects RAG code only when present.
**UNDERSTAND GATE:** You can explain the fallback order (why NVIDIA first — free/strong; why Groq fallback — rate-limit insurance) and why RAG injection is conditional (graceful degrade to V2 if retrieval is empty).
**IF IT BREAKS:** NVIDIA auth error → check NVIDIA_API_KEY + base_url. JSON parse error → confirm response_format json is set. Fix the specific call; keep the cascade design.

## TASK 3.2 — Fix the telemetry in main.py
**GOAL:** Store the REAL provider/model, not hardcoded "groq".
**IDE INSTRUCTION:**
```
main.py currently hardcodes model_provider="groq" and model_name="llama-3.3-70b-versatile" when writing to Supabase. Update it to use the provider_name and model_name now returned by evaluate_and_enrich, so telemetry reflects which provider actually served each issue. Also store retrieved_chunk_ids and retrieval_method ('RRF' when chunks were used, 'NONE' when empty). Explain why truthful telemetry matters for observability.
```
**DONE WHEN:** Supabase issues rows show the actual provider/model used + retrieved_chunk_ids populated.
**UNDERSTAND GATE:** You can explain why hardcoded telemetry is dangerous (your dashboards would lie; you couldn't measure fallback rate).
**IF IT BREAKS:** Column missing → confirm 03_alter_issues ran on the new project.

---

# ═══════════════════════════════════════
# PHASE 4 — FULL PIPELINE ON 3-5 REPOS
# ═══════════════════════════════════════

## TASK 4.1 — Run the complete pipeline on 3-5 varied repos
**GOAL:** Prove the whole V3 flow works end-to-end across languages.
**IDE INSTRUCTION:**
```
Configure main.py to run the FULL pipeline (Stage A hunt → pre-filter → DeBERTa → grounding → RAG retrieve → LLM gateway → post-validate → quality score → store) on exactly these repos: fastapi/fastapi (Python), facebook/react (JS), huggingface/transformers (ML/Python). Run it. Then show me SQL to inspect the stored issues: confirm they have ai_hint, quality_grade, model_provider (real), and retrieved_chunk_ids. Walk me through 2-3 stored hints — are they grounded in real code (do they cite real files from the retrieved chunks)?
```
**DONE WHEN:** Issues from all 3 repos are stored with grounded hints, real telemetry, and quality grades.
**UNDERSTAND GATE:** You can trace one issue's full journey through all stages and explain what each stage did to it.
**IF IT BREAKS:** Expect bugs here — this is the first full integration. Fix per-stage; the error message names the failing stage. Do NOT redesign; patch the specific failure and re-run.

---

# ═══════════════════════════════════════
# PHASE 5 — EVAL (the interview number)
# ═══════════════════════════════════════

## TASK 5.1 — Build the ground-truth extractor
**GOAL:** Auto-build golden dataset from real merged PRs.
**IDE INSTRUCTION:**
```
Write scripts/build_golden_set.py that, for a set of CLOSED issues from my indexed repos:
1. Uses the GitHub API timeline/events endpoint to find the PR that CLOSED each issue.
2. Checks the PR is actually merged (merged == true via the API field — not AI, just the field).
3. Fetches that PR's changed files (the files list).
4. For PRs that changed multiple files, uses an LLM (NVIDIA) ONLY to judge which 1-2 files are the CORE fix (vs tests/config/formatting) — this is the judgment step.
5. Writes a golden CSV: issue_id, issue_title, repo, ground_truth_files.
Skip issues with no cleanly linked merged PR. Aim for 15-20 clean rows. Explain each function. Make clear which parts are FACTS (GitHub API: merged status, changed files) vs JUDGMENT (LLM: which file is the core fix).
```
**DONE WHEN:** A golden CSV exists with 15-20 issues mapped to real core fix files.
**UNDERSTAND GATE:** You can explain why this isn't circular (ground truth = real merged PR, not an LLM guess; LLM only picks core-file from real changed files).
**IF IT BREAKS:** Few issues resolve to PRs → that's expected; lower the target to 10-15. The API can't link every issue to a PR.

## TASK 5.2 — Run the retrieval + hint eval
**GOAL:** Produce your real precision number.
**IDE INSTRUCTION:**
```
Rewrite scripts/evaluate_pipeline.py to use the golden CSV. For each golden issue:
1. RETRIEVAL metric: run retrieve_code_for_issue and check if any ground_truth_file appears in the retrieved chunks' file paths. Compute retrieval recall = (issues where the right file was retrieved) / total.
2. HINT metric: run the full pipeline's hint and check if it references the ground_truth_file. Compute file-match precision.
Print both numbers clearly with the counts (e.g. "Retrieval recall: 13/18 = 72%"). Store results in a Supabase eval_results table. Explain what each number means.
```
**DONE WHEN:** The script prints retrieval recall % and hint file-match % with real counts.
**UNDERSTAND GATE:** You can state your two numbers and what each measures (retrieval = did RAG find the right code; hint = did the final output point to the right file).
**IF IT BREAKS:** 0% → check snapshot ACTIVE + commit_sha alignment between index and eval. A real low number is fine and honest — report it; do not fudge it.

---

# ═══════════════════════════════════════
# PHASE 6 — SCALE + POLISH (only after 1-5 work)
# ═══════════════════════════════════════

## TASK 6.1 — Scale to all 65 repos
**IDE INSTRUCTION:**
```
Now that the pipeline works on 3 repos, scale main.py to all 65 repos across the 6 categories. Add model caching for the embedding model so GitHub Actions doesn't re-download it each run. Warn me about the 90-min Action timeout and where the bottleneck will be (CPU embedding), and propose a per-run repo batch limit if needed.
```
**DONE WHEN:** Full run completes within limits; DB populated across categories.
**UNDERSTAND GATE:** You can explain the scaling bottlenecks (API limits, CPU embedding, Action timeout) and your mitigations.

## TASK 6.2 — Continuous eval (optional, impressive)
**IDE INSTRUCTION:**
```
Wrap evaluate_pipeline.py in a weekly GitHub Action that samples recent issues, runs the eval, and stores scores in eval_results over time. This gives continuous quality tracking. Keep it within NVIDIA's ~40 req/min limit.
```
**DONE WHEN:** A scheduled workflow runs the eval and logs scores.

## TASK 6.3 — Polish for proof
**IDE INSTRUCTION:**
```
Update the README with: the architecture (Mermaid diagram), the real eval numbers, the differentiator line ("existing tools list labeled issues; GitNova generates verified code-grounded tactical plans"), and the tech stack. Keep it honest — numbers only as measured.
```
**DONE WHEN:** README tells the full story with real numbers.

---

# ═══════════════════════════════════════
# THE DISCIPLINE RULES (re-read when stuck)
# ═══════════════════════════════════════
1. **One task at a time.** Current task's DONE WHEN must be true before the next.
2. **Fix, don't redesign.** A bug is a bug. The architecture is locked. No model-swapping, no re-planning, no "what if I did it differently" mid-build.
3. **Understand before advancing.** Can't explain it → ask the IDE to explain → then move.
4. **First-run errors are normal.** Expect them per phase. They are not "the project is broken."
5. **No new scope.** If you think of an improvement, write it in a "LATER.md" file and keep building. Do not implement it now.
6. **Stop = the project works on 3-5 repos with a real eval number.** That is the finish line for the core build. Everything after (scale, automation, polish) is bonus.

---

# WHAT "DONE" LOOKS LIKE (the finish line)
- V3 pipeline runs end-to-end on 3-5 repos ✅
- Hints are grounded in real retrieved code ✅
- Telemetry shows real provider/model ✅
- A real eval number exists from real merged-PR ground truth ✅
- You can explain every component in an interview ✅

When those 5 are true, the core build is DONE. Scale and polish next. Then update the resume with the number, record a 2-min Loom, and start applying.

---
*This is the locked execution plan. No more planning. Execute Phase 0, Task 0.1 next. One task at a time. Fix, don't redesign. Build.*
