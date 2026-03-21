from __future__ import annotations

from tools import load_resume_text
import os
import json
import re
from config import settings
from .llm_utils import extract_json_block, safe_json_loads

AGENT_ID = "resume_analysis"
AGENT_NAME = "Resume Analysis Agent"
DEFAULT_MODEL = settings.OPENAI_MODEL_RESUME_ANALYSIS
TOOLS = ["load_resume_text"]



def run(state: dict, *, model: str = DEFAULT_MODEL) -> dict:
    resume_text = state.get("resume_text")
    resume_path = state.get("resume_path")

    if not resume_text:
        if resume_path:
            resume_text = load_resume_text(resume_path)
        else:
            raise ValueError("No resume provided. Please input a resume path or paste resume text.")

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI
        print("[resume_analysis] LangChain imports OK")
    except ModuleNotFoundError as e:
        print("[resume_analysis] LangChain imports failed:", str(e))

        return {
            "candidate_profile": profile,
            "resume_evidence": evidence,
            "messages": [
                {
                    "role": "assistant",
                    "name": AGENT_NAME,
                    "content": "Resume parsed (fallback mode). Candidate profile created.",
                }
            ],
        }

    system = """You are the Resume Analysis Agent for CareerPilot AI.

Your task is to extract structured information from a resume text.

IMPORTANT RULES:
- Extract as much relevant information as possible from the text.
- DO NOT leave fields empty if information can be reasonably extracted.
- DO NOT infer or hallucinate information that is not present.
- If a field is partially available, fill what you can.
- Ignore phone numbers, exact addresses, or sensitive personal data.

SECTION UNDERSTANDING:
- "KEY SKILLS", "Technical", "Skills" → skills section
- "EDUCATION" → education section
- "EXPERIENCE", "WORK EXPERIENCE" → experience section
- Bullet points (•, -, etc.) and "|" separators should be parsed into lists

FIELD EXTRACTION RULES:

Name:
- Usually the first line of the resume
- Extract full name if present

Headline:
- Professional summary or role description
- If not explicitly present, use short summary line if available
- Otherwise return empty string

Skills:
- Extract all technical and soft skills
- Split by commas, "|", "/", or bullet points
- Include technologies, tools, and frameworks

Education:
- Each entry should include:
  - school (university or institution name)
  - degree (if available)
  - field (if available)
  - dates (if available)
- If multiple lines belong to same education, combine them

Experience:
- Each entry should include:
  - company (if identifiable)
  - role/title
  - dates (if available)
  - highlights (bullet points under that role)

Links:
- Extract URLs or emails

Certifications:
- Extract any certification or qualification mentioned

OUTPUT REQUIREMENTS:
- Output ONLY valid JSON (no explanation, no markdown)
- All fields must exist in the JSON
- Use empty list [] or empty string "" if truly not available

JSON SCHEMA:
{
  "profile": {
    "name": string,
    "headline": string,
    "education": [ { "school": string, "degree": string, "field": string, "dates": string } ],
    "experience": [ { "company": string, "role": string, "dates": string, "highlights": [string] } ],
    "skills": [string],
    "certifications": [string],
    "links": [string]
  },
  "evidence": {
    "skills": [ { "skill": string, "snippets": [string] } ],
    "education": [ { "school": string, "degree": string, "field": string, "dates": string } ],
    "experience": [ { "company": string, "role": string, "dates": string, "highlights": [string] } ]
  }
}
"""

    api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
    print("[resume_analysis] OPENAI_API_KEY exists:", bool(api_key))
    print("[resume_analysis] resume_text preview:")
    print((resume_text or "")[:2000])

    llm = ChatOpenAI(
        model=model,
        temperature=0,
        api_key=api_key,
        model_kwargs={"response_format": {"type": "json_object"}},
    )

    try:
        resp = llm.invoke([
            SystemMessage(content=system),
            HumanMessage(content=resume_text[:20000]),
        ])
    except Exception as e:
        print("[resume_analysis] LLM invoke failed:", str(e))
        raise

    print("[resume_analysis] resp.content type:", type(resp.content))
    print("[resume_analysis] raw content:")
    print(resp.content)

    raw = resp.content if isinstance(resp.content, str) else json.dumps(resp.content, ensure_ascii=False)
    raw = raw.strip()

    payload = safe_json_loads(raw)
    if payload is None:
        jb = extract_json_block(raw)
        print("[resume_analysis] extracted json block:", jb)
        payload = safe_json_loads(jb or "")

    if payload is None:
        payload = {
            "profile": {
                "name": "",
                "headline": "",
                "education": [],
                "experience": [],
                "skills": [],
                "certifications": [],
                "links": [],
            },
            "evidence": {
                "skills": [],
                "education": [],
                "experience": [],
            },
            "raw": raw,
        }

    print("[resume_analysis] final payload:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    profile = payload.get("profile") or {}
    evidence = payload.get("evidence") or {}


    return {
        "candidate_profile": {
            "name": profile.get("name", ""),
            "headline": profile.get("headline", ""),
            "education": profile.get("education", []),
            "experience": profile.get("experience", []),
            "skills": profile.get("skills", []),
            "certifications": profile.get("certifications", []),
            "links": profile.get("links", []),
        },
        "resume_evidence": {
            "skills": evidence.get("skills", []),
            "education": evidence.get("education", []),
            "experience": evidence.get("experience", []),
        },
        "messages": [
            {
                "role": "assistant",
                "name": AGENT_NAME,
                "content": "Resume parsed. Candidate profile created.",
            }
        ],
    }