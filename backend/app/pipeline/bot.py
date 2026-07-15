"""
GitNova LLM Judge — Production Tactical Prompt
===============================================
Rewritten prompt with:
- Banned generic verbs
- Repo grounding injection
- Confidence scoring
- INSUFFICIENT CONTEXT fallback
- File extension enforcement
"""

import os
import time
import json
from groq import Groq
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Initialize Clients
groq_key = os.getenv("GROQ_API_KEY")
if not groq_key:
    raise ValueError("❌ CRITICAL: GROQ_API_KEY is missing from .env")
groq = Groq(api_key=groq_key, max_retries=1)

nvidia_key = os.getenv("NVIDIA_API_KEY")
nvidia_client = None
if nvidia_key:
    nvidia_client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=nvidia_key,
        max_retries=1
    )
else:
    print("⚠️ WARNING: NVIDIA_API_KEY is missing. NVIDIA NIM will be skipped.")


SYSTEM_PROMPT = """You are an expert open-source code reviewer. Your job is to verify issue difficulty and produce a CONCRETE tactical fix plan.

You will receive: an issue title, issue body, repository context, and RETRIEVED CODE EVIDENCE (real code chunks from the repository).

THINK IN TWO STEPS:

STEP 1 — ANALYZE: Is this issue a specific, actionable bug or feature request?
  - If the issue is a vague rant, an epic, or asks for architectural redesign → output "Reject" for difficulty.
  - If the issue describes a specific behavior problem → proceed to Step 2.

STEP 2 — COMMIT: Using ONLY the retrieved code evidence, identify the exact file and function that needs to change.
  - You MUST name at least one specific file from the retrieved code evidence.
  - You MUST name at least one class, function, or method from that file.
  - If multiple files could be relevant, pick the MOST LIKELY one based on the issue description.
  - Do NOT say you cannot determine the file. The retrieved code was selected specifically for this issue — use it.

STRICT RULES — VIOLATIONS WILL BE REJECTED:

1. BANNED VERBS — NEVER output generic fixes like 'add a null check', 'insert a case branch',
   or 'add an if statement' unless the issue explicitly mentions these.
   Do NOT use generic verbs like 'Review', 'Investigate', 'Test', 'Update', 'Modify', 'Check', 'Ensure', 'Implement'.

2. FILE PATHS — Every file path MUST:
   - Come from the retrieved code evidence (do NOT invent paths)
   - Use the correct extension for this repository's language
   - Reference directories that actually appear in the evidence

3. CONCRETE IDENTIFIERS — You MUST name at least one:
   - Specific class, function, or method name FROM the retrieved code
   - Specific variable, constant, or config key
   - NO generic references like "the relevant function" or "the appropriate module"

4. NO SDLC BOILERPLATE — Do not write generic steps like "Write tests" or "Document changes".

5. CONFIDENCE — Rate your confidence 0-100:
   - 90-100: You can identify exact files and functions from the code evidence
   - 60-89: You can identify likely files; functions are educated guesses
   - 30-59: You can narrow to an area of code from the evidence
   - Below 30: Set difficulty to "Reject" (issue is genuinely too vague)

6. CRITICAL: If retrieved code evidence IS provided, you MUST use it to name a file.
   Only output "Reject" when the issue itself is genuinely vague AND no relevant code was retrieved.
   A difficult issue with relevant code evidence is NOT a reason to reject — commit to your best analysis.
"""


def build_user_prompt(issue_title: str, issue_body: str, repo: str, 
                       initial_difficulty: str, repo_context: dict,
                       retrieved_code: str = "", retry_feedback: list = None) -> str:
    """Build the user prompt with repo grounding, retrieved code, and optional retry feedback."""
    
    grounding = repo_context.get("grounding_block", f"Repository: {repo}")
    valid_exts = repo_context.get("valid_extensions", [])
    ext_note = f"This is a {repo_context.get('language', 'Unknown')} repository. All file paths MUST use {', '.join(valid_exts)} extensions." if valid_exts else ""
    
    prompt = f"""--- REPOSITORY CONTEXT ---
{grounding}
{ext_note}
"""

    if retrieved_code:
        prompt += f"""
--- RETRIEVED CODE EVIDENCE ---
{retrieved_code}
"""

    prompt += f"""
--- ISSUE ---
Title: {issue_title}
Body: {issue_body[:5000]}

--- TASK ---
Initial difficulty classification: {initial_difficulty}

Verify the difficulty and produce a tactical plan based on the retrieved code evidence above.

Output JSON (strict schema):
{{
    "verified_difficulty": "Novice" | "Apprentice" | "Contributor" | "Reject",
    "reason": "One sentence explaining your classification",
    "confidence": <0-100>,
    "hint": "**🎯 Goal:** [One concrete sentence]\\n\\n**📂 Files:**\\n- `path/to/specific/file.ext`\\n\\n**🔧 Change:**\\n1. In `ClassName.method_name()`, [specific action]\\n2. [Next specific action]"
}}"""

    if retry_feedback:
        feedback_str = "; ".join(retry_feedback)
        prompt += f"""

⚠️ RETRY: Your previous output was rejected for: {feedback_str}
Be MORE SPECIFIC this time. Name exact classes, functions, and file paths. 
Do NOT use any banned verbs. Use the repository context above to ground your file paths."""

    return prompt


def evaluate_and_enrich(issue_title: str, issue_body: str, repo: str, 
                         initial_difficulty: str, repo_context: dict = None,
                         retrieved_code: str = "", retry_feedback: list = None) -> tuple:
    """
    Call the LLM to evaluate and enrich an issue.
    
    Args:
        issue_title: The issue's title
        issue_body: The issue's body text
        repo: The repo name (e.g., "facebook/react")
        initial_difficulty: DeBERTa's classification
        repo_context: Dict from get_repo_context() with grounding info
        retrieved_code: Text context containing matching code chunks
        retry_feedback: Optional list of validation failure reasons (for retries)
    
    Returns:
        A tuple of (response_json_str, provider_name, model_name), or (None, None, None) if all models fail.
    """
    if repo_context is None:
        repo_context = {"grounding_block": f"Repository: {repo}", "valid_extensions": []}
    
    print(f"      ⚡ The Judge is reviewing ({repo})...")
    
    # 🛑 SAFE MODE: RATE LIMIT PROTECTION
    time.sleep(2)

    # Establish priority list: try in order, skip if client unavailable.
    # Gemma 4 is primary temporarily since Llama 3.3 is currently down/timing out on NVIDIA NIM.
    # Added strict 25s timeout to prevent API hangs.
    models = []
    if nvidia_client:
        models.append({"provider": "nvidia", "name": "google/gemma-4-31b-it",        "client": nvidia_client})
        models.append({"provider": "nvidia", "name": "meta/llama-3.3-70b-instruct", "client": nvidia_client})

    models.extend([
        {"provider": "groq", "name": "qwen/qwen3.6-27b",                       "client": groq},
        {"provider": "groq", "name": "meta/llama-4-scout-17b-16e-instruct",     "client": groq}
    ])
    
    if not issue_body:
        issue_body = "No details provided."
 
    user_prompt = build_user_prompt(
        issue_title, issue_body, repo, 
        initial_difficulty, repo_context, retrieved_code, retry_feedback
    )
 
    for model_info in models:
        provider = model_info["provider"]
        model_name = model_info["name"]
        client = model_info["client"]
        
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
                timeout=25.0  # Safe timeout to prevent indefinite hangs
            )
            return completion.choices[0].message.content, provider, model_name
            
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "timeout" in error_str.lower():
                print(f"      ⚠️ Rate limit or timeout on {provider}/{model_name}. Switching brain... 🔄")
                continue
            else:
                print(f"      ❌ {provider} Error ({model_name}): {e}. Trying next...")
                continue
 
    print("      🛑 All brains exhausted. Skipping this issue.")
    return None, None, None