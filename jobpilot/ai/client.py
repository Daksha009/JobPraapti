"""Optional asynchronous Gemini client; imports only when AI is enabled."""

from ..config import settings


async def generate_text(prompt: str, *, json_output=False) -> str:
    from google import genai

    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY is not configured")
    async with genai.Client(
        api_key=settings.gemini_api_key, http_options={"timeout": 30000}
    ).aio as client:
        response = await client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config={"response_mime_type": "application/json"} if json_output else None,
        )
        return response.text or ""
