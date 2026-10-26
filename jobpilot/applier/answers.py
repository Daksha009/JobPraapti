"""Job-specific written answers built from local evidence, never inferred facts.

Only narrative questions use this composer. Screening facts and consent must
come from explicit profile or per-job answers. No resume is sent to an API.
"""

import json
import re
from pathlib import Path


def read_resume(path: Path) -> str:
    try:
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages[:10])[
                :40000
            ]
    except Exception:
        return ""


def load_answer_record(value: str) -> dict:
    try:
        record = json.loads(value or "{}")
        return record if isinstance(record, dict) and record.get("version") == 1 else {}
    except (TypeError, ValueError):
        return {}


def has_term(term: str, text: str) -> bool:
    return bool(re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, re.I))


class AnswerComposer:
    def __init__(self, profile, job, resume_text=""):
        self.profile, self.job, self.resume_text = profile, job, resume_text
        self.record = {"version": 1, "entries": [], "unresolved": []}
        previous = load_answer_record(job.generated_answers)
        # Keep manually prepared drafts available when the live form is resumed.
        entries = previous.get("entries", [])
        if isinstance(entries, list):
            self.record["entries"] = [
                entry
                for entry in entries
                if isinstance(entry, dict) and isinstance(entry.get("question"), str)
            ]
        overrides = previous.get("overrides", {})
        self.record["overrides"] = overrides if isinstance(overrides, dict) else {}

    def remember(self, question, answer, source, evidence=""):
        entries = self.record["entries"]
        entries[:] = [item for item in entries if item["question"] != question]
        entries.append(
            {
                "question": question,
                "answer": answer,
                "source": source,
                "evidence": evidence,
            }
        )

    def narrative(self, question: str, kind: str) -> str | None:
        if not self.profile.get("application_defaults", {}).get(
            "compose_narrative_answers", False
        ):
            return None
        if kind not in ("text", "textarea"):
            return None
        label = question.casefold()
        # An open text field may still request a factual declaration.
        if re.search(
            r"\b(visa|sponsor\w*|authori[sz]\w*|salary|ctc|compensation|consent|background check|criminal|disability|gender|race|ethnic\w*|veteran|notice period|years?|date|graduat\w*|citizen\w*|relocat\w*|how many|certif\w*|clearance|eligible|availability)\b",
            label,
        ):
            return None
        interest = bool(
            re.search(
                r"why.*(interest|join|work|apply|applying|company|role)|what interests",
                label,
            )
        )
        background = bool(
            re.search(
                r"tell us about yourself|introduce yourself|professional summary|cover letter|what makes you.*(fit|candidate)|why.*(hire|fit)|describe.*(background|experience|project)|relevant (experience|project)",
                label,
            )
        )
        if not interest and not background:
            return None
        # Search cards often have only a title. Require a real job description.
        if not self.job.description.strip():
            return None
        jd = self.job.description
        skills = [
            str(skill)
            for skill in self.profile.get("preferences", {}).get("skills", [])
            if has_term(str(skill), self.resume_text) and has_term(str(skill), jd)
        ]
        if not skills:
            return None
        # Keep an intact resume bullet, including its continuation lines.
        bullets = []
        active = False
        for line in self.resume_text.splitlines():
            line = line.strip()
            if line.startswith(("•", "- ", "●")):
                bullets.append(line.lstrip("•●- "))
                active = True
            elif (
                active
                and line
                and not line.isupper()
                and not re.search(r"\b(20\d{2}|EXPERIENCE|PROJECTS|SKILLS)\b", line)
            ):
                bullets[-1] += " " + line
            elif line:
                # Prevent a following heading from being appended to a bullet.
                active = False
        relevant = [
            b
            for b in bullets
            if b and len(b) <= 700 and any(has_term(s, b) for s in skills)
        ]
        relevant.sort(key=lambda b: sum(has_term(s, b) for s in skills), reverse=True)
        evidence = relevant[0] if relevant else ""
        if not evidence:
            return None
        skill_list = ", ".join(skills[:4])
        target = self.job.title.strip()[:180]
        company = self.job.company.strip()[:120]
        if company and not company.lower().startswith("unknown"):
            target += f" at {company}"
        if interest:
            answer = f"I'm interested in the {target} role because it aligns with my work in {skill_list}. "
        else:
            answer = f"My background includes hands-on work with {skill_list}, which is relevant to the {target} role. "
        answer += f"One example from my resume is: “{evidence}” "
        answer += "I'd welcome the opportunity to contribute this experience and continue developing these skills with your team."
        self.remember(question, answer, "resume_and_job", evidence)
        return answer

    def resolve(self, info, default):
        from .forms import normalize

        label = info["label"]
        overrides = {normalize(k): v for k, v in self.record["overrides"].items()}
        if normalize(label) in overrides:
            answer = overrides[normalize(label)]
            self.remember(label, answer, "user")
            return answer
        if default is not None and default != "":
            self.remember(label, default, "profile")
            return default
        return self.narrative(label, info["type"])
