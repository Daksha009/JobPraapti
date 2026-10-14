"""Bounded, local PDF skill extraction for profile uploads. No external API calls."""

import io
import re
import unicodedata
import pdfplumber
from .ai.resume_parser import extract_keywords_regex

DISPLAY = {
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "node.js": "Node.js",
    "reactjs": "React",
    "react.js": "React",
    "react": "React",
    "nextjs": "Next.js",
    "next.js": "Next.js",
    "vuejs": "Vue.js",
    "vue.js": "Vue.js",
    "vue": "Vue.js",
    "nodejs": "Node.js",
    "golang": "Go",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "mongodb": "MongoDB",
    "mysql": "MySQL",
    "fastapi": "FastAPI",
    "github": "GitHub",
    "gitlab": "GitLab",
    "scikit-learn": "scikit-learn",
    "pytorch": "PyTorch",
    "tensorflow": "TensorFlow",
    "asp.net": "ASP.NET",
    ".net": ".NET",
    "springboot": "Spring Boot",
    "tailwindcss": "Tailwind CSS",
    "tailwind": "Tailwind CSS",
    "k8s": "Kubernetes",
    "kubernetes": "Kubernetes",
}
UPPER = {
    "aws",
    "gcp",
    "sql",
    "html",
    "html5",
    "css",
    "css3",
    "ci/cd",
    "rest api",
    "jwt",
    "saml",
    "sre",
    "dsa",
    "oop",
    "tdd",
    "bdd",
    "sdlc",
    "r",
    "c++",
    "c#",
    "ec2",
    "s3",
    "ecs",
    "eks",
    "rds",
    "sqs",
}


def unique(values):
    result, seen = [], set()
    for value in values:
        clean = re.sub(r"\s+", " ", value).strip()
        if clean and clean.casefold() not in seen:
            result.append(clean)
            seen.add(clean.casefold())
    return result


def inspect_pdf(payload):
    if len(payload) > 5 * 1024 * 1024 or not payload.startswith(b"%PDF-"):
        raise ValueError("Resume must be a PDF up to 5 MB")
    try:
        with pdfplumber.open(io.BytesIO(payload)) as pdf:
            if not pdf.pages or len(pdf.pages) > 30:
                raise ValueError("Use a resume with 1–30 pages")
            parts = [(page.extract_text() or "") for page in pdf.pages]
            text = unicodedata.normalize("NFKC", "\n".join(parts))[:120000]
    except ValueError:
        raise
    except Exception:
        raise ValueError(
            "The PDF could not be read. Try an unprotected, text-based PDF."
        ) from None
    parsed = extract_keywords_regex(text)
    ordered = sorted(
        parsed["skills"], key=lambda skill: (text.lower().find(skill), -len(skill))
    )
    skills = unique(
        [
            DISPLAY.get(skill, skill.upper() if skill in UPPER else skill.title())
            for skill in ordered
        ]
    )
    warning = ""
    if not text.strip():
        warning = "This PDF has no selectable text. Upload a text-based PDF or add skills manually; scanned pages need OCR."
    elif not skills:
        warning = "No skills from the local vocabulary were recognized. Add your skills and search keywords below."
    # Portfolio links can mention GitHub before any substantive resume skills.
    # Keep those skills, but prefer more discriminating job-search terms first.
    general_tools = {"git", "github", "gitlab", "bitbucket"}
    keywords = [skill for skill in skills if skill.casefold() not in general_tools]
    keywords += [skill for skill in skills if skill.casefold() in general_tools]
    return {
        "skills": skills,
        "search_keywords": keywords[:8],
        "warning": warning,
        "pages": len(parts),
        "method": "local",
        "text_characters": len(text),
    }
