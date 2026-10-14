"""
Resume Parser — Extracts keywords, skills, and profile data from a PDF resume.
Uses pdfplumber for text extraction and optionally Gemini for intelligent parsing.
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ─── Known skill / technology keywords (for regex fallback) ──────────────
KNOWN_SKILLS = {
    # Languages
    "python",
    "java",
    "javascript",
    "typescript",
    "c++",
    "c#",
    "go",
    "golang",
    "rust",
    "ruby",
    "php",
    "swift",
    "kotlin",
    "scala",
    "r",
    "matlab",
    "perl",
    "sql",
    "html",
    "css",
    "html5",
    "css3",
    "sass",
    "less",
    # Frontend
    "react",
    "reactjs",
    "react.js",
    "angular",
    "angularjs",
    "vue",
    "vuejs",
    "vue.js",
    "next.js",
    "nextjs",
    "nuxt",
    "nuxtjs",
    "svelte",
    "gatsby",
    "tailwind",
    "tailwindcss",
    "bootstrap",
    "material ui",
    "mui",
    "jquery",
    # Backend
    "node.js",
    "nodejs",
    "express",
    "expressjs",
    "express.js",
    "django",
    "flask",
    "fastapi",
    "spring",
    "spring boot",
    "springboot",
    ".net",
    "asp.net",
    "rails",
    "ruby on rails",
    "laravel",
    "nestjs",
    "nest.js",
    # Databases
    "mysql",
    "postgresql",
    "postgres",
    "mongodb",
    "redis",
    "elasticsearch",
    "cassandra",
    "dynamodb",
    "sqlite",
    "oracle",
    "mssql",
    "sql server",
    "firebase",
    "firestore",
    "supabase",
    "neo4j",
    "graphql",
    # Cloud & DevOps
    "aws",
    "azure",
    "gcp",
    "google cloud",
    "ec2",
    "s3",
    "lambda",
    "cloudwatch",
    "cloudformation",
    "ecs",
    "eks",
    "fargate",
    "rds",
    "docker",
    "kubernetes",
    "k8s",
    "terraform",
    "ansible",
    "jenkins",
    "ci/cd",
    "github actions",
    "gitlab ci",
    "circleci",
    "nginx",
    "apache",
    "linux",
    "unix",
    "bash",
    "shell scripting",
    "powershell",
    # Tools & Platforms
    "git",
    "github",
    "gitlab",
    "bitbucket",
    "jira",
    "confluence",
    "figma",
    "postman",
    "swagger",
    "grafana",
    "prometheus",
    "datadog",
    "splunk",
    "new relic",
    "sentry",
    "kibana",
    "logstash",
    # Data & AI/ML
    "pandas",
    "numpy",
    "scikit-learn",
    "tensorflow",
    "pytorch",
    "keras",
    "opencv",
    "nltk",
    "spacy",
    "hugging face",
    "transformers",
    "power bi",
    "tableau",
    "looker",
    "apache spark",
    "hadoop",
    "kafka",
    "airflow",
    "dbt",
    "snowflake",
    "databricks",
    "bigquery",
    # Concepts
    "rest api",
    "restful",
    "microservices",
    "monolith",
    "serverless",
    "event-driven",
    "message queue",
    "rabbitmq",
    "sqs",
    "pub/sub",
    "websocket",
    "grpc",
    "soap",
    "oauth",
    "jwt",
    "saml",
    "agile",
    "scrum",
    "kanban",
    "sdlc",
    "tdd",
    "bdd",
    "unit testing",
    "integration testing",
    "e2e testing",
    "data structures",
    "algorithms",
    "dsa",
    "oop",
    "object-oriented programming",
    "design patterns",
    "solid",
    "system design",
    "distributed systems",
    "caching",
    "load balancing",
    "api gateway",
    "service mesh",
    "machine learning",
    "deep learning",
    "natural language processing",
    "computer vision",
    "data science",
    "data engineering",
    "devops",
    "sre",
    "site reliability",
    "cloud computing",
    "blockchain",
    "web3",
    "smart contracts",
    "solidity",
}

# Role / title keywords for search query generation
ROLE_KEYWORDS = {
    "software engineer",
    "software developer",
    "backend developer",
    "frontend developer",
    "full stack developer",
    "fullstack developer",
    "web developer",
    "mobile developer",
    "android developer",
    "ios developer",
    "devops engineer",
    "cloud engineer",
    "data engineer",
    "data scientist",
    "machine learning engineer",
    "ml engineer",
    "ai engineer",
    "sre",
    "site reliability engineer",
    "qa engineer",
    "test engineer",
    "sdet",
    "embedded engineer",
    "systems engineer",
    "platform engineer",
    "solutions architect",
    "technical lead",
    "engineering manager",
    "intern",
    "sde",
    "swe",
    "associate",
    "junior",
    "trainee",
}


def extract_text_from_pdf(pdf_path: str | Path) -> str:
    """Extract all text from a PDF file using pdfplumber."""
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"Resume PDF not found: {pdf_path}")

    try:
        import pdfplumber
    except ImportError:
        raise ImportError(
            "pdfplumber is required for resume parsing. "
            "Install it with: pip install pdfplumber"
        )

    text_parts = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)

    full_text = "\n".join(text_parts)
    logger.info(
        f"[resume_parser] Extracted {len(full_text)} characters from {pdf_path.name}"
    )
    return full_text


def extract_keywords_regex(text: str) -> Dict[str, List[str]]:
    """
    Extract skills and role keywords from resume text using pattern matching.
    This is the fast, offline fallback when Gemini API is unavailable.
    """
    text_lower = text.lower()

    # ── Extract matching skills ──
    found_skills: Set[str] = set()
    for skill in KNOWN_SKILLS:
        # Respect tokens and language punctuation: JavaScript is not Java; C++ is not C#.
        pattern = r"(?<![\w+#])" + re.escape(skill) + r"(?![\w+#])"
        if re.search(pattern, text_lower):
            found_skills.add(skill)

    # ── Extract role keywords ──
    found_roles: Set[str] = set()
    for role in ROLE_KEYWORDS:
        if re.search(r"(?<!\w)" + re.escape(role) + r"(?!\w)", text_lower):
            found_roles.add(role)

    # ── Extract certifications (common patterns) ──
    certs = []
    cert_patterns = [
        r"(?:certified|certification)\s+[\w\s]+",
        r"AWS\s+(?:Certified\s+)?[\w\s]+(?:Associate|Professional)",
        r"Google\s+(?:Cloud\s+)?(?:Certified\s+)?[\w\s]+",
        r"Azure\s+[\w\s]+(?:Fundamentals|Associate|Expert)",
    ]
    for pattern in cert_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        certs.extend([m.strip() for m in matches if len(m.strip()) > 5])

    # ── Extract years of experience ──
    exp_years = None
    exp_patterns = [
        r"(\d+)\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience|exp)",
        r"experience\s*[:\-]?\s*(\d+)\+?\s*(?:years?|yrs?)",
    ]
    for pattern in exp_patterns:
        match = re.search(pattern, text_lower)
        if match:
            exp_years = int(match.group(1))
            break

    # ── Extract education keywords ──
    education = []
    edu_patterns = [
        r"(?:B\.?Tech|B\.?E\.?|B\.?Sc|M\.?Tech|M\.?S\.?|M\.?Sc|MBA|PhD|Ph\.D)",
        r"(?:Bachelor|Master|Doctorate)\s+(?:of|in)\s+[\w\s]+",
        r"(?:Computer Science|Information Technology|Electronics|Electrical)",
    ]
    for pattern in edu_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        education.extend([m.strip() for m in matches])

    return {
        "skills": sorted(found_skills),
        "roles": sorted(found_roles),
        "certifications": list(set(certs)),
        "education": list(set(education)),
        "experience_years": exp_years,
    }


async def extract_keywords_ai(text: str) -> Optional[Dict[str, List[str]]]:
    """
    Use Google Gemini to intelligently extract structured profile data from resume text.
    Returns None if API is unavailable.
    """
    from ..config import settings

    api_key = settings.gemini_api_key
    if not api_key:
        logger.warning("[resume_parser] No Gemini API key — skipping AI extraction")
        return None

    try:
        from .client import generate_text

        prompt = f"""Analyze the following resume text and extract structured information.

RESUME TEXT:
{text[:4000]}

Respond ONLY with a valid JSON object (no markdown, no code fences):
{{
    "skills": ["skill1", "skill2", ...],
    "roles": ["target role 1", "target role 2", ...],
    "certifications": ["cert1", "cert2", ...],
    "education": ["degree1", "degree2", ...],
    "experience_years": <integer or null>,
    "summary": "<1-2 sentence professional summary>",
    "search_queries": ["query1", "query2", ...]
}}

Rules:
- "skills" should include ALL technical skills, tools, frameworks, languages, and platforms mentioned.
- "roles" should include job titles the candidate is suited for based on their experience.
- "search_queries" should be 5-8 search terms that would find relevant jobs for this candidate on platforms like LinkedIn, Glassdoor, etc.
- Be thorough with skills — include both specific (e.g. "React") and general (e.g. "Frontend Development") terms.
"""

        response_text = (await generate_text(prompt, json_output=True)).strip()

        # Clean markdown code fences if present
        if response_text.startswith("```"):
            response_text = response_text.split("\n", 1)[1]
        if response_text.endswith("```"):
            response_text = response_text.rsplit("```", 1)[0]
        response_text = response_text.strip()

        result = json.loads(response_text)
        logger.info(
            f"[resume_parser] AI extracted {len(result.get('skills', []))} skills, "
            f"{len(result.get('roles', []))} roles"
        )
        return result

    except Exception as e:
        logger.warning(f"[resume_parser] AI extraction failed: {e}")
        return None


class ResumeParser:
    """
    High-level resume parser that combines PDF extraction + AI/regex keyword extraction.

    Usage:
        parser = ResumeParser("config/resume.pdf")
        keywords = await parser.parse()
        print(keywords["skills"])
        print(keywords["search_queries"])
    """

    def __init__(self, pdf_path: str | Path = None):
        from ..config import settings

        self.pdf_path = Path(pdf_path) if pdf_path else settings.resume_path

    async def parse(self, use_ai: bool = True) -> Dict[str, any]:
        """
        Parse the resume and extract structured keyword data.

        Args:
            use_ai: If True, attempt Gemini AI extraction first, with regex fallback.
                    If False, use only regex-based extraction.

        Returns:
            Dict with keys: skills, roles, certifications, education,
                            experience_years, summary, search_queries
        """
        # Step 1: Extract raw text from PDF
        text = extract_text_from_pdf(self.pdf_path)

        if not text.strip():
            logger.warning("[resume_parser] No text extracted from PDF")
            return self._empty_result()

        # Step 2: Try AI extraction first (more accurate)
        ai_result = None
        if use_ai:
            ai_result = await extract_keywords_ai(text)

        # Step 3: Always run regex extraction for completeness
        regex_result = extract_keywords_regex(text)

        # Step 4: Merge results (AI primary, regex fills gaps)
        if ai_result:
            merged = self._merge_results(ai_result, regex_result)
        else:
            merged = regex_result
            # Generate search queries from regex results
            merged["search_queries"] = self._generate_search_queries(merged)
            merged["summary"] = ""

        # Store the raw text for reference
        merged["raw_text"] = text

        logger.info(
            f"[resume_parser] Final extraction: "
            f"{len(merged.get('skills', []))} skills, "
            f"{len(merged.get('roles', []))} roles, "
            f"{len(merged.get('search_queries', []))} search queries"
        )

        return merged

    def _merge_results(self, ai_result: Dict, regex_result: Dict) -> Dict:
        """Merge AI and regex results, preferring AI but adding regex findings."""
        merged = {
            "skills": list(
                set(
                    [s.lower() for s in ai_result.get("skills", [])]
                    + regex_result.get("skills", [])
                )
            ),
            "roles": list(
                set(
                    [r.lower() for r in ai_result.get("roles", [])]
                    + regex_result.get("roles", [])
                )
            ),
            "certifications": list(
                set(
                    ai_result.get("certifications", [])
                    + regex_result.get("certifications", [])
                )
            ),
            "education": list(
                set(ai_result.get("education", []) + regex_result.get("education", []))
            ),
            "experience_years": (
                ai_result.get("experience_years")
                if ai_result.get("experience_years") is not None
                else regex_result.get("experience_years")
            ),
            "summary": ai_result.get("summary", ""),
            "search_queries": ai_result.get("search_queries", []),
        }

        # If AI didn't provide search queries, generate them
        if not merged["search_queries"]:
            merged["search_queries"] = self._generate_search_queries(merged)

        return merged

    def _generate_search_queries(self, data: Dict) -> List[str]:
        """Generate platform search queries from extracted skills and roles."""
        queries = []

        # Add role-based queries
        for role in data.get("roles", [])[:5]:
            queries.append(role.title())

        # Add skill-based queries
        top_skills = data.get("skills", [])[:8]
        if top_skills:
            queries.append(f"{'  '.join(s.title() for s in top_skills[:3])} Developer")

        # Add combo queries
        roles = data.get("roles", [])
        skills = data.get("skills", [])
        if roles and skills:
            queries.append(f"{roles[0].title()} {skills[0].title()}")

        return queries[:8]

    def _empty_result(self) -> Dict:
        """Return empty result structure."""
        return {
            "skills": [],
            "roles": [],
            "certifications": [],
            "education": [],
            "experience_years": None,
            "summary": "",
            "search_queries": [],
            "raw_text": "",
        }
