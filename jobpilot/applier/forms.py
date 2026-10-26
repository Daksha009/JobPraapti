"""Fill known answers only. Unknown questions are returned for human review."""

import re
from pathlib import Path


def normalize(label: str) -> str:
    label = re.sub(r"([a-z])([A-Z])", r"\1 \2", label)
    return re.sub(r"[^a-z0-9]+", " ", label.lower()).strip()


def choice_key(value: str) -> str:
    """Preserve meaningful punctuation in choices such as C, C++ and C#."""
    return " ".join(value.casefold().split())


def choice_matches(question: str, answer: str, option: str) -> bool:
    if choice_key(answer) == choice_key(option):
        return True
    key = normalize(question)
    if key in ("notice period", "what is your notice period"):
        immediate = {
            "immediate",
            "immediately available",
            "immedidately available",
            "available immediately",
        }
        return normalize(answer) in immediate and normalize(option) in immediate
    if key == "which state city are you based in":
        # Only exact city names from the saved location; no nearby-city inference.
        return choice_key(answer.split(",")[0]) == choice_key(option.split(":")[-1])
    return False


def phone_country_option(options: list[dict], phone: str):
    """Derive only an unambiguous calling-code option from an international phone."""
    phone = re.sub(r"[\s().-]", "", str(phone))
    if not re.fullmatch(r"\+\d{7,15}", phone):
        return None
    matches = []
    for option in options:
        code = re.search(r"\(\+(\d{1,4})\)\s*$", option["label"])
        if code and not option["disabled"] and phone[1:].startswith(code[1]):
            matches.append(option)
    return matches[0] if len(matches) == 1 else None


def answer_for(label: str, profile: dict):
    key = normalize(label)
    personal = profile.get("personal", {})
    defaults = profile.get("application_defaults", {})
    explicit = {normalize(k): v for k, v in defaults.get("answers", {}).items()}
    if key in explicit:
        return explicit[key]
    # These declarations are used only after the user saves them explicitly.
    if key in (
        "do you require visa sponsorship",
        "will you now or in the future require sponsorship for employment visa status e g h 1b etc",
        "will you now or in the future require sponsorship for employment visa status",
        "do you need visa sponsorship",
    ):
        return defaults.get("visa_sponsorship_required")
    if key in (
        "are you legally authorized to work in india",
        "are you authorized to work in india",
        "do you have the right to work in india",
    ):
        return defaults.get("work_authorization", {}).get("India")
    if key in (
        "do you consent to a background check",
        "we conduct thorough background checks as part of our hiring process by selecting yes you acknowledge and consent to this verification if you advance in the process",
    ):
        return defaults.get("background_check_consent")
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
        "which state city are you based in": "location",
        "linkedin": "linkedin_url",
        "linkedin url": "linkedin_url",
        "linkedin profile": "linkedin_url",
        "github": "github_url",
        "github url": "github_url",
        "github portfolio url": "github_url",
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
        "what is your expected ctc": "expected_ctc",
        "expected salary range": "expected_ctc",
        "expected salary": "expected_ctc",
        "what is your notice period": "notice_period",
        "current ctc": "current_ctc",
        "what is your current ctc": "current_ctc",
        "message": "intro_message",
        "note": "intro_message",
        "cover letter": "cover_letter",
        "willing to relocate": "willing_to_relocate",
    }
    return defaults.get(aliases.get(key, ""))


FIELD_INFO = """el => {
  const labelText = node => {const copy = node.cloneNode(true); copy.querySelectorAll('input,select,textarea,button').forEach(e => e.remove()); return copy.textContent.trim();};
  const fieldset = el.closest('fieldset, [role="radiogroup"]');
  let legend = fieldset?.querySelector('legend')?.textContent || fieldset?.getAttribute('aria-label');
  if (el.type === 'radio' && el.name && el.getAttribute('aria-label')) {
    const peers = Array.from(document.querySelectorAll('input[type="radio"]')).filter(r => r.name === el.name);
    if (peers.every(r => r.getAttribute('aria-label') === el.getAttribute('aria-label'))) legend = el.getAttribute('aria-label');
  }
  if (el.type === 'radio' && !legend && el.name) {
    for (let parent = el.parentElement, depth = 0; parent && depth < 8; parent = parent.parentElement, depth++) {
      const radios = Array.from(parent.querySelectorAll('input[type="radio"]'));
      if (radios.some(r => r.name !== el.name)) break;
      if (radios.length < 2) continue;
      const heading = Array.from(parent.querySelectorAll('label,legend,p,div')).find(n =>
        !n.querySelector('input,select,textarea') && !n.closest('label:has(input)') && n.textContent.trim());
      if (heading) { legend = heading.textContent.trim(); break; }
    }
  }
  const labelled = (el.getAttribute('aria-labelledby') || '').split(' ')
    .map(id => document.getElementById(id)?.textContent || '').join(' ').trim();
  // Some forms wrap inputs in a label with a broken `for` attribute.
  const wrapping = el.closest('label');
  const wrappedLabel = wrapping && wrapping.querySelectorAll('input,select,textarea').length === 1 ? labelText(wrapping) : '';
  let optionLabel = Array.from(el.labels || []).map(labelText).join(' ').trim() || wrappedLabel;
  if (el.type === 'radio' && !optionLabel) {
    for (let parent = el.parentElement, depth = 0; parent && depth < 4; parent = parent.parentElement, depth++) {
      if (parent.querySelectorAll('input,select,textarea').length !== 1) break;
      const text = labelText(parent);
      if (text) { optionLabel = text; break; }
    }
  }
  const label = el.type === 'radio' ? (legend || el.name) :
    (labelled || el.getAttribute('aria-label') || Array.from(el.labels || []).map(labelText).join(' ') || wrappedLabel || el.placeholder || el.name || el.id);
  return {label: (label || '').trim(), type: el.type || el.tagName.toLowerCase(),
          tag: el.tagName.toLowerCase(), required: el.required || el.getAttribute('aria-required') === 'true',
          value: el.value || '', checked: el.checked, valid: el.checkValidity ? el.checkValidity() : true,
          maxLength: el.maxLength ?? -1,
          ariaLabel: el.getAttribute('aria-label') || '',
          optionLabel};
}"""


async def validation_errors(scope) -> list[str]:
    """Read field-associated site errors, including custom text-input validation."""
    errors = []
    for field in await scope.locator("input, select, textarea").all():
        if not await field.is_visible() or await field.is_disabled():
            continue
        invalid = await field.evaluate(r"""el => {
          if (el.getAttribute('aria-invalid') === 'true' || !el.checkValidity()) return true;
          const ids = [el.getAttribute('aria-describedby'), el.getAttribute('aria-errormessage')].filter(Boolean).join(' ').split(/\s+/);
          return ids.some(id => {
            const node = document.getElementById(id);
            return node && node.getClientRects().length &&
              /\b(invalid input|enter a valid|required field|must be a number)\b/i.test(node.textContent);
          });
        }""")
        if invalid:
            info = await field.evaluate(FIELD_INFO)
            errors.append(info["label"] or "Unlabelled question")
    return sorted(set(errors))


async def fill_form(
    scope, profile: dict, resume_path: Path, composer=None
) -> list[str]:
    unresolved = []
    radio_seen = {}
    phone_code = ""
    for field in await scope.locator("input, select, textarea").all():
        info = await field.evaluate(FIELD_INFO)
        kind, label = info["type"], info["label"]
        if kind in ("hidden", "submit", "button", "reset") or await field.is_disabled():
            continue
        if kind != "file" and not await field.is_visible():
            wrapper = field.locator("xpath=ancestor::label[1]")
            # Some sites put the visible label beside an offscreen native input.
            if not await wrapper.count():
                identity = await field.get_attribute("id")
                for candidate in await scope.locator("label").all():
                    if identity and await candidate.get_attribute("for") == identity:
                        wrapper = candidate
                        break
            if (
                kind not in ("radio", "checkbox")
                or not await wrapper.count()
                or not await wrapper.is_visible()
            ):
                continue
        answer = answer_for(label, profile)
        if (
            answer is None
            and kind == "checkbox"
            and not info["required"]
            and re.fullmatch(
                r"follow .+ to stay up to date with their page", normalize(label)
            )
        ):
            # Applying does not imply opting into a company's social updates.
            answer = False
        if composer is not None:
            answer = composer.resolve(info, answer)
        if (
            answer is None
            and info["tag"] == "select"
            and normalize(label) == "phone country code"
        ):
            options = await field.locator("option").evaluate_all(
                "els => els.map(e => ({label:e.textContent.trim(), value:e.value, disabled:e.disabled}))"
            )
            option = phone_country_option(
                options, profile.get("personal", {}).get("phone", "")
            )
            if option is not None:
                await field.select_option(value=option["value"])
                phone_code = re.search(r"\(\+(\d{1,4})\)\s*$", option["label"])[1]
                continue
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
            if (
                composer is not None
                and composer.record.get("resume_uploaded") == info["ariaLabel"]
                and info["checked"]
            ):
                group["selected"] = True
                continue
            if answer is not None:
                value = (
                    "Yes"
                    if answer is True
                    else "No"
                    if answer is False
                    else str(answer)
                )
                if any(
                    choice_matches(label, value, option)
                    for option in (info["value"], info["optionLabel"])
                ):
                    if await field.is_visible():
                        await field.check()
                    else:
                        await wrapper.click()
                    group["selected"] = await field.is_checked()
            continue
        if kind == "checkbox":
            if answer is not None and isinstance(answer, bool):
                if await field.is_visible():
                    await field.set_checked(answer)
                elif await field.is_checked() != answer:
                    await wrapper.click()
                if await field.is_checked() != answer:
                    unresolved.append(label or "Unanswered checkbox")
            else:
                unresolved.append(label or "Unanswered checkbox")
            if info["required"] and not await field.is_checked():
                unresolved.append(label or "Required checkbox")
            continue
        if answer is None:
            unresolved.append(label or "Unlabelled question")
            continue
        value = "Yes" if answer is True else "No" if answer is False else str(answer)
        if phone_code and normalize(label) in (
            "phone",
            "phone number",
            "mobile",
            "mobile phone number",
            "mobile number",
        ):
            # A separate calling-code control expects a national phone number.
            compact = re.sub(r"[\s().-]", "", value)
            if compact.startswith("+" + phone_code):
                value = compact[len(phone_code) + 1 :]
        if info["maxLength"] >= 0 and len(value) > info["maxLength"]:
            unresolved.append(label)
            continue
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
                        and any(
                            choice_matches(label, value, option)
                            for option in (o["label"], o["value"])
                        )
                    ),
                    None,
                )
                if option is None:
                    unresolved.append(label)
                    continue
                await field.select_option(value=option["value"])
                if normalize(label) == "phone country code":
                    code = re.search(r"\(\+(\d{1,4})\)\s*$", option["label"])
                    phone_code = code[1] if code else ""
            else:
                await field.fill(value)
                await field.blur()
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
        if (
            await custom.is_visible()
            and not await custom.locator("input,select,textarea").count()
        ):
            unresolved.append(
                await custom.get_attribute("aria-label") or "Custom form control"
            )
    rejected = await validation_errors(scope)
    unresolved = sorted(set(unresolved + rejected))
    if composer is not None:
        composer.record["unresolved"] = unresolved
        composer.record["validation_errors"] = rejected
    return unresolved
