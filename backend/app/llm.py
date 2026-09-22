import json
import time

from google import genai
from google.genai import types

from .config import settings


client = genai.Client(
    api_key=settings.gemini_api_key
)


# Primary model comes from backend/.env
# Fallback model is used if the primary model
# temporarily returns 429 or 503.
MODELS = [
    settings.llm_model,
    "gemini-3.5-flash-lite",
]


def is_temporary_error(error):
    error_text = str(error)

    return (
        "503" in error_text
        or "429" in error_text
        or "UNAVAILABLE" in error_text
        or "RESOURCE_EXHAUSTED" in error_text
    )


def generate_with_retry(prompt, model, json_mode=False):
    max_retries = 3

    for attempt in range(max_retries):
        try:
            if json_mode:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    ),
                )
            else:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                )

            return response.text or ""

        except Exception as error:
            if not is_temporary_error(error):
                raise

            if attempt == max_retries - 1:
                raise

            wait_seconds = 2 ** attempt

            print(
                f"Gemini model {model} temporarily unavailable. "
                f"Retry {attempt + 1}/{max_retries} "
                f"in {wait_seconds}s...",
                flush=True,
            )

            time.sleep(wait_seconds)


def answer_question(question, sources):
    if not sources:
        return (
            "No indexed code was found. "
            "Please index the repository first."
        )

    context = "\n\n".join(
        (
            f"FILE: {source['path']}:"
            f"{source['start_line']}-"
            f"{source['end_line']}\n"
            f"{source['content']}"
        )
        for source in sources
    )

    prompt = f"""
You are Codebase AI, a precise senior software engineer.

Answer the user's question using ONLY the supplied repository evidence.

Do not invent:

- files
- functions
- classes
- line numbers
- implementation details

If the evidence is insufficient, clearly say so.

IMPORTANT:
The repository evidence may contain only retrieved chunks from larger files.
Do not assume that a file or function ends where a retrieved chunk ends.

User question:

{question}

Repository evidence:

{context}

Give a concise technical answer.

When possible, cite the relevant file path and line range.
"""

    last_error = None

    for model in MODELS:
        print(
            f"Trying Gemini model: {model}",
            flush=True,
        )

        try:
            answer = generate_with_retry(
                prompt,
                model,
            )

            if answer:
                print(
                    f"Gemini model succeeded: {model}",
                    flush=True,
                )

                return answer

        except Exception as error:
            last_error = error

            print(
                f"Model {model} failed: {error}",
                flush=True,
            )

            continue

    raise RuntimeError(
        f"All Gemini generation models failed. "
        f"Last error: {last_error}"
    )


def _parse_review_json(raw_text):
    """
    Safely parse Gemini's structured review response.
    Handles normal JSON and accidental markdown code fences.
    """

    text = raw_text.strip()

    if text.startswith("```"):
        lines = text.splitlines()

        if lines and lines[0].startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"Gemini returned invalid review JSON: {error}"
        ) from error

    if not isinstance(data, dict):
        raise RuntimeError(
            "Gemini review response must be a JSON object."
        )

    findings = data.get("findings", [])

    if not isinstance(findings, list):
        raise RuntimeError(
            "Gemini review field 'findings' must be an array."
        )

    summary = data.get("summary", {})

    if not isinstance(summary, dict):
        summary = {}

    return {
        "findings": findings,
        "summary": summary,
        "overall_review": data.get(
            "overall_review",
            ""
        ),
    }


def review_repository(sources):
    if not sources:
        return {
            "findings": [],
            "summary": {
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
                "informational": 0,
                "potential": 0,
            },
            "overall_review": (
                "No relevant repository code was found "
                "for review."
            ),
        }

    evidence_blocks = []

    for index, source in enumerate(sources, start=1):
        evidence_blocks.append(
            f"""
SOURCE {index}

FILE:
{source['path']}

LINES:
{source['start_line']}-{source['end_line']}

IMPORTANT:
This is a RETRIEVED CODE CHUNK from the file.

The chunk may start in the middle of a function,
class, SQL statement, expression, or logical block.

The chunk may also end in the middle of a function,
class, SQL statement, expression, or logical block.

Therefore:

- Do NOT assume the file ends at the last displayed line.
- Do NOT assume the function ends at the last displayed line.
- Do NOT call code incomplete merely because the chunk ends abruptly.
- Do NOT report a syntax error unless the supplied code itself clearly proves it.
- Do NOT interpret retrieval boundaries as source-code boundaries.

CODE:

{source['content']}
"""
        )

    context = "\n".join(evidence_blocks)

    prompt = f"""
You are a senior software engineer performing a
careful code review of a real software repository.

Review ONLY the exact repository evidence supplied below.

Your review must be evidence-based.

==================================================
REVIEW CATEGORIES
==================================================

- Security
- Bug
- Error Handling
- Performance
- Code Quality
- Configuration
- Architecture

==================================================
CRITICAL EVIDENCE RULES
==================================================

1. Use ONLY the supplied repository evidence.

2. Do NOT invent:
   - files
   - functions
   - classes
   - vulnerabilities
   - line numbers
   - implementation details
   - dependencies
   - APIs

3. The supplied evidence consists of RETRIEVED CHUNKS.

4. A retrieved chunk is NOT necessarily the complete file.

5. Never assume that the beginning of a chunk is the
   beginning of a function, class, SQL query, or block.

6. Never assume that the end of a chunk is the end of
   a function, class, SQL query, or block.

7. A code statement appearing incomplete at the end
   of a retrieved chunk is NOT by itself a bug.

8. Do NOT report an incomplete SQL query simply because
   the SQL continues beyond the retrieved chunk.

9. Do NOT report a syntax error unless the actual
   supplied code clearly demonstrates invalid syntax.

10. Before reporting a finding, verify that every:
    - file path
    - function name
    - class name
    - variable name
    - code fragment

    mentioned in the finding actually appears in the
    supplied repository evidence.

11. Never rely on memory of previous versions of the
    repository.

12. Review ONLY the exact evidence supplied in this request.

13. If additional repository context is required,
    classify the issue as a potential issue.

14. Prefer fewer high-confidence findings over many
    speculative findings.

15. Do not duplicate findings.

16. Do not manufacture findings to make the review
    appear comprehensive.

==================================================
SEVERITY
==================================================

Critical:
Severe issue that could cause major compromise,
data loss, or complete system failure.

High:
Significant security, correctness, or reliability issue.

Medium:
Meaningful issue with realistic negative impact.

Low:
Minor issue with limited practical impact.

Informational:
Observation or improvement suggestion.

==================================================
FINDING RULE
==================================================

A confirmed finding requires sufficient evidence.

If evidence only suggests a problem, set:

"potential": true

and:

"confidence": "Low"

Never present an uncertain issue as confirmed.

==================================================
OUTPUT FORMAT
==================================================

Return ONLY valid JSON.

Use exactly this structure:

{{
  "findings": [
    {{
      "category": "Security",
      "severity": "Medium",
      "title": "Short descriptive title",
      "explanation": "Evidence-based explanation.",
      "file": "backend/app/config.py",
      "lines": "14-16",
      "evidence": "Specific evidence from the supplied code.",
      "recommended_fix": "Practical technical recommendation.",
      "confidence": "High",
      "potential": false
    }}
  ],
  "summary": {{
    "critical": 0,
    "high": 0,
    "medium": 0,
    "low": 0,
    "informational": 0,
    "potential": 0
  }},
  "overall_review": "Short evidence-based overall assessment."
}}

==================================================
IMPORTANT OUTPUT RULES
==================================================

- findings must be an array.
- summary values must be integers.
- potential must be true or false.
- confidence must be High, Medium, or Low.
- severity must be Critical, High, Medium, Low, or Informational.
- category must be one of the specified review categories.
- File paths and line ranges must come from the supplied evidence.
- Do not include markdown.
- Do not include explanations outside the JSON.
- If no confirmed problems exist, return an empty findings array.
- Do not create a finding merely because a pattern is unusual.

==================================================
REPOSITORY EVIDENCE
==================================================

{context}
"""

    last_error = None

    for model in MODELS:
        print(
            f"Trying review model: {model}",
            flush=True,
        )

        try:
            raw_answer = generate_with_retry(
                prompt,
                model,
                json_mode=True,
            )

            if raw_answer:
                review = _parse_review_json(raw_answer)

                print(
                    f"Review model succeeded: {model}",
                    flush=True,
                )

                return review

        except Exception as error:
            last_error = error

            print(
                f"Review model failed: {error}",
                flush=True,
            )

            continue

    raise RuntimeError(
        f"All Gemini review models failed. "
        f"Last error: {last_error}"
    )