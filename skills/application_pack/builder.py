from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agents.supervisor import resolve_target_job


def _pick_job(state: dict[str, Any], job_id: str | None) -> dict[str, Any]:
    matches = list(state.get("job_matches") or [])
    if job_id:
        for j in matches:
            if str(j.get("id") or "") == job_id.strip():
                return dict(j)
    target = resolve_target_job(state)
    if target.get("id") or target.get("title"):
        return dict(target)
    return dict(matches[0]) if matches else {}


def _cover_letter_draft(
    profile: dict[str, Any],
    job: dict[str, Any],
    hooks: list[str],
    resume_suggestions: dict[str, Any],
) -> str:
    name = str(profile.get("name") or "Candidate").strip()
    title = str(job.get("title") or "the role").strip()
    company = str(job.get("company") or "your organization").strip()
    headline = str(profile.get("headline") or profile.get("summary") or "").strip()
    skills = profile.get("skills") or []
    skill_line = ", ".join(str(s) for s in skills[:6]) if skills else "relevant technical skills"
    summary_tip = str(resume_suggestions.get("summary_tip") or "").strip()

    hook_lines = [str(h).strip() for h in hooks if str(h).strip()]
    body_hook = hook_lines[0] if hook_lines else f"I am excited to apply for {title}."

    paragraphs = [
        "Dear Hiring Manager,",
        "",
        f"I am writing to express my interest in the {title} position at {company}. "
        f"{body_hook}",
        "",
    ]
    if headline:
        paragraphs.append(headline)
        paragraphs.append("")
    paragraphs.append(
        f"My background includes {skill_line}. I believe these strengths align with your "
        f"requirements for {title}."
    )
    if summary_tip:
        paragraphs.extend(["", summary_tip])
    if len(hook_lines) > 1:
        paragraphs.extend(["", hook_lines[1]])
    paragraphs.extend(
        [
            "",
            "I would welcome the opportunity to discuss how I can contribute to your team. "
            "Thank you for your time and consideration.",
            "",
            "Sincerely,",
            name,
        ]
    )
    return "\n".join(paragraphs)


def _follow_up_email_draft(profile: dict[str, Any], job: dict[str, Any]) -> str:
    name = str(profile.get("name") or "Candidate").strip()
    title = str(job.get("title") or "the position").strip()
    company = str(job.get("company") or "your company").strip()
    return (
        f"Subject: Following up — {title} application\n\n"
        f"Dear Hiring Manager,\n\n"
        f"I hope this message finds you well. I submitted my application for the {title} role "
        f"at {company} last week and wanted to reiterate my enthusiasm for the opportunity.\n\n"
        f"I remain very interested in contributing my skills to your team. Please let me know "
        f"if any additional information would be helpful.\n\n"
        f"Thank you,\n{name}"
    )


def build_application_pack(
    state: dict[str, Any],
    *,
    run_id: str | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    """
    Merge resume suggestions, apply strategy, and job context into one application pack.
    No LLM call — deterministic assembly for export and UI preview.
    """
    profile = dict(state.get("candidate_profile") or {})
    resume_suggestions = dict(state.get("resume_suggestions") or {})
    apply_strategy = dict(state.get("apply_strategy") or {})
    gaps = dict(state.get("skill_gaps") or {})
    job = _pick_job(state, job_id)

    hooks = list(apply_strategy.get("cover_letter_hooks") or [])
    checklist = list(apply_strategy.get("follow_up_checklist") or [])
    if not checklist:
        checklist = [
            "Review tailored resume bullets below before submitting.",
            "Customize the cover letter opening for this employer.",
            "Apply within 5–7 days while the posting is active.",
            "Set a calendar reminder to follow up in 7–10 days.",
        ]

    bullets = list(resume_suggestions.get("experience_bullets") or [])
    ats_keywords = list(resume_suggestions.get("ats_keywords") or [])
    missing = gaps.get("missing_skills") or []

    pack = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "run_id": run_id,
        "job": {
            "id": str(job.get("id") or ""),
            "title": str(job.get("title") or ""),
            "company": str(job.get("company") or ""),
            "score": job.get("score"),
            "skills_required": list(job.get("skills_required") or [])[:12],
        },
        "candidate": {
            "name": str(profile.get("name") or ""),
            "headline": str(profile.get("headline") or ""),
            "skills": list(profile.get("skills") or [])[:20],
        },
        "resume_section": {
            "summary_tip": str(resume_suggestions.get("summary_tip") or ""),
            "experience_bullets": bullets,
            "ats_keywords": ats_keywords,
        },
        "cover_letter_draft": _cover_letter_draft(profile, job, hooks, resume_suggestions),
        "follow_up_email_draft": _follow_up_email_draft(profile, job),
        "checklist": checklist,
        "timing_advice": str(apply_strategy.get("timing_advice") or ""),
        "skill_gaps_to_address": [
            m.get("skill") if isinstance(m, dict) else str(m) for m in missing[:8]
        ],
        "notes": list(apply_strategy.get("notes") or resume_suggestions.get("notes") or []),
    }
    return pack
