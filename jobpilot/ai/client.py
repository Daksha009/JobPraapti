"""Optional asynchronous Gemini client; imports only when AI is enabled."""

import logging

from ..config import settings

logger = logging.getLogger(__name__)
FALLBACK_MODEL = "gemini-2.5-flash"


async def generate_text(prompt: str, *, json_output=False) -> str:
    from google import genai

    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY is not configured")
    async with genai.Client(
        api_key=settings.gemini_api_key, http_options={"timeout": 30000}
    ).aio as client:
        config = {"response_mime_type": "application/json"} if json_output else None
        try:
            response = await client.models.generate_content(
                model=settings.gemini_model, contents=prompt, config=config
            )
        except Exception as exc:
            # A listed model may temporarily be unavailable even with a valid key.
            # Do not retry authentication, quota, validation, or other failures.
            if (
                getattr(exc, "code", None) != 503
                or settings.gemini_model == FALLBACK_MODEL
            ):
                raise
            logger.warning("Gemini model unavailable (503); trying %s", FALLBACK_MODEL)
            response = await client.models.generate_content(
                model=FALLBACK_MODEL, contents=prompt, config=config
            )
        return response.text or ""
