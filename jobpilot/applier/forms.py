"""Fill known answers only. Unknown questions are returned for human review."""

import re
from pathlib import Path


def normalize(label: str) -> str:
    label = re.sub(r"([a-z])([A-Z])", r"\1 \2", label)
    return re.sub(r"[^a-z0-9]+", " ", label.lower()).strip()


def choice_key(value: str) -> str:
    """Preserve meaningful punctuation in choices such as C, C++ and C#."""
    return " ".join(value.casefold().split())


def answer_for(label: str, profile: dict):
    key = normalize(label)
    personal = profile.get("personal", {})
    defaults = profile.get("application_defaults", {})
    explicit = {normalize(k): v for k, v in defaults.get("answers", {}).items()}
    if key in explicit:
        return explicit[key]
    aliases = {
        "name": "full_name",
        "full name": "full_name",
        "first name": "first_name",
        "last name": "last_name",
        "email": "email",
        "email address": "email",
        "phone": "phone",
        "phone number": "phone",
        "mobile": "phone",
        "mobile phone number": "phone",
        "mobile number": "phone",
        "city": "location",
        "location": "location",
        "current location": "location",
        "linkedin": "linkedin_url",
        "linkedin url": "linkedin_url",
        "linkedin profile": "linkedin_url",
        "github": "github_url",
        "github url": "github_url",
        "portfolio": "portfolio_url",
        "website": "portfolio_url",
    }
    if key in aliases:
        return personal.get(aliases[key])
    aliases = {
        "years of experience": "years_of_experience",
        "total experience": "years_of_experience",
        "total years of experience": "years_of_experience",
        "notice period": "notice_period",
        "expected ctc": "expected_ctc",
        "current ctc": "current_ctc",
        "message": "intro_message",
        "note": "intro_message",
        "cover letter": "cover_letter",
        "willing to relocate": "willing_to_relocate",
    }
    return defaults.get(aliases.get(key, ""))


FIELD_INFO = """el => {
  const labelText = node => {const copy = node.cloneNode(true); copy.querySelectorAll('input,select,textarea,button').forEach(e => e.remove()); return copy.textContent.trim();};
  const fieldset = el.closest('fieldset, [role="radiogroup"]');
  const legend = fieldset?.querySelector('legend')?.textContent || fieldset?.getAttribute('aria-label');
  const labelled = (el.getAttribute('aria-labelledby') || '').split(' ')
    .map(id => document.getElementById(id)?.textContent || '').join(' ').trim();
  const label = el.type === 'radio' ? (legend || el.name) :
    (labelled || el.getAttribute('aria-label') || Array.from(el.labels || []).map(labelText).join(' ') || el.placeholder || el.name || el.id);
  return {label: (label || '').trim(), type: el.type || el.tagName.toLowerCase(),
          tag: el.tagName.toLowerCase(), required: el.required || el.getAttribute('aria-required') === 'true',
          value: el.value || '', checked: el.checked, valid: el.checkValidity ? el.checkValidity() : true,
          optionLabel: Array.from(el.labels || []).map(labelText).join(' ').trim()};
}"""


async def fill_form(scope, profile: dict, resume_path: Path) -> list[str]:
    unresolved = []
    radio_seen = {}
    for field in await scope.locator("input, select, textarea").all():
        info = await field.evaluate(FIELD_INFO)
        kind, label = info["type"], info["label"]
        if kind in ("hidden", "submit", "button", "reset") or await field.is_disabled():
            continue
        if kind != "file" and not await field.is_visible():
            continue
        answer = answer_for(label, profile)
        if kind == "file":
            # Hidden native file controls commonly back a visible upload button.
            if not re.search(r"\b(resume|cv)\b", normalize(label)):
                unresolved.append(label or "Unlabelled file upload")
            elif resume_path.is_file():
                await field.set_input_files(str(resume_path))
            else:
                unresolved.append(f"Resume missing: {resume_path.name}")
            continue
        if kind == "radio":
            group = radio_seen.setdefault(
                label, {"selected": False, "required": info["required"]}
            )
            if answer is not None:
                value = (
                    "Yes"
                    if answer is True
                    else "No"
                    if answer is False
                    else str(answer)
                )
                if choice_key(value) in (
                    choice_key(info["value"]),
                    choice_key(info["optionLabel"]),
                ):
                    await field.check()
                    group["selected"] = True
            continue
        if kind == "checkbox":
            if answer is not None and isinstance(answer, bool):
                await field.set_checked(answer)
            else:
                unresolved.append(label or "Unanswered checkbox")
            if info["required"] and not await field.is_checked():
                unresolved.append(label or "Required checkbox")
            continue
        if answer is None:
            unresolved.append(label or "Unlabelled question")
            continue
        value = "Yes" if answer is True else "No" if answer is False else str(answer)
        try:
            if info["tag"] == "select":
                options = await field.locator("option").evaluate_all(
                    "els => els.map(e => ({label:e.textContent.trim(), value:e.value, disabled:e.disabled}))"
                )
                option = next(
                    (
                        o
                        for o in options
                        if not o["disabled"]
                        and choice_key(value)
                        in (choice_key(o["label"]), choice_key(o["value"]))
                    ),
                    None,
                )
                if option is None:
                    unresolved.append(label)
                    continue
                await field.select_option(value=option["value"])
            else:
                await field.fill(value)
            if not await field.evaluate("el => el.checkValidity()"):
                unresolved.append(label)
        except Exception:
            unresolved.append(label or "Unsupported input")
    unresolved.extend(
        label for label, state in radio_seen.items() if not state["selected"]
    )
    for custom in await scope.locator(
        '[role="combobox"]:not(input):not(select), [role="radio"]:not(input), [role="checkbox"]:not(input), [contenteditable="true"]'
    ).all():
        if await custom.is_visible():
            unresolved.append(
                await custom.get_attribute("aria-label") or "Custom form control"
            )
    return sorted(set(unresolved))
