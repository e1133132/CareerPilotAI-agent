from __future__ import annotations

import io
import json
import re
import zipfile
from typing import Any


def _safe_filename_part(value: str, fallback: str = "application") -> str:
    cleaned = re.sub(r"[^\w\-]+", "_", (value or "").strip(), flags=re.UNICODE)
    return (cleaned[:48] or fallback).strip("_")


def pack_to_markdown(pack: dict[str, Any]) -> str:
    job = pack.get("job") or {}
    cand = pack.get("candidate") or {}
    resume = pack.get("resume_section") or {}
    lines = [
        "# CareerPilot Application Pack",
        "",
        f"**Generated:** {pack.get('generated_at', '')}",
        f"**Candidate:** {cand.get('name') or '—'}",
        f"**Target role:** {job.get('title') or '—'} @ {job.get('company') or '—'}",
        "",
        "---",
        "",
        "## Resume tips",
        "",
    ]
    if resume.get("summary_tip"):
        lines.extend([str(resume["summary_tip"]), ""])

    bullets = resume.get("experience_bullets") or []
    if bullets:
        lines.append("### Suggested experience bullets")
        lines.append("")
        for b in bullets:
            if not isinstance(b, dict):
                continue
            section = b.get("section") or "Experience"
            suggested = b.get("suggested") or b.get("original") or ""
            lines.append(f"**{section}**")
            lines.append(f"- {suggested}")
            lines.append("")

    keywords = resume.get("ats_keywords") or []
    if keywords:
        lines.append(f"**ATS keywords:** {', '.join(str(k) for k in keywords)}")
        lines.append("")

    gaps = pack.get("skill_gaps_to_address") or []
    if gaps:
        lines.append(f"**Gaps to address in interview:** {', '.join(str(g) for g in gaps)}")
        lines.append("")

    lines.extend(["---", "", "## Cover letter draft", "", pack.get("cover_letter_draft") or "", ""])
    lines.extend(["---", "", "## Follow-up email draft", "", pack.get("follow_up_email_draft") or "", ""])

    checklist = pack.get("checklist") or []
    if checklist:
        lines.extend(["---", "", "## Application checklist", ""])
        for i, item in enumerate(checklist, 1):
            lines.append(f"{i}. {item}")
        lines.append("")

    if pack.get("timing_advice"):
        lines.extend(["**Timing:** " + str(pack["timing_advice"]), ""])

    notes = pack.get("notes") or []
    if notes:
        lines.extend(["---", "", "## Notes", ""])
        for n in notes:
            lines.append(f"- {n}")

    return "\n".join(lines).strip() + "\n"


def pack_to_zip_bytes(pack: dict[str, Any]) -> bytes:
    job = pack.get("job") or {}
    # title = _safe_filename_part(str(job.get("title") or "role"))
    # company = _safe_filename_part(str(job.get("company") or "company"))
    

    resume_md = ["# Resume suggestions", ""]
    resume = pack.get("resume_section") or {}
    if resume.get("summary_tip"):
        resume_md.extend(["## Summary tip", "", str(resume["summary_tip"]), ""])
    for b in resume.get("experience_bullets") or []:
        if isinstance(b, dict):
            resume_md.append(f"## {b.get('section') or 'Experience'}")
            resume_md.append(f"Original: {b.get('original') or ''}")
            resume_md.append(f"Suggested: {b.get('suggested') or ''}")
            resume_md.append(f"Rationale: {b.get('rationale') or ''}")
            resume_md.append("")
    kw = resume.get("ats_keywords") or []
    if kw:
        resume_md.append("## ATS keywords")
        resume_md.append(", ".join(str(k) for k in kw))

    checklist_md = ["# Application checklist", ""]
    for i, item in enumerate(pack.get("checklist") or [], 1):
        checklist_md.append(f"{i}. {item}")
    if pack.get("timing_advice"):
        checklist_md.extend(["", f"**Timing:** {pack['timing_advice']}"])

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.md", pack_to_markdown(pack))
        zf.writestr("cover_letter.md", (pack.get("cover_letter_draft") or "") + "\n")
        zf.writestr("follow_up_email.txt", (pack.get("follow_up_email_draft") or "") + "\n")
        zf.writestr("resume_suggestions.md", "\n".join(resume_md).strip() + "\n")
        zf.writestr("checklist.md", "\n".join(checklist_md).strip() + "\n")
        zf.writestr("pack.json", json.dumps(pack, ensure_ascii=False, indent=2))
    return buf.getvalue()


def zip_download_filename(pack: dict[str, Any]) -> str:
    job = pack.get("job") or {}
    title = _safe_filename_part(str(job.get("title") or "application"))
    return f"careerpilot_{title}_pack.zip"
