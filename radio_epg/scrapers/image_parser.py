"""Parse a schedule screenshot using the Anthropic Claude API (vision)."""

from __future__ import annotations

import base64
import json
import re


_PROMPT = """Look at this image of a radio or TV station schedule and extract all programme listings.

Return ONLY a JSON object in this exact format — no explanation, no markdown fences:
{
  "days": {
    "weekdays": [
      {"start": "06:00", "title": "Morning Show", "presenter": "Host Name", "description": "Brief description"}
    ],
    "saturday": [
      {"start": "06:00", "title": "Weekend Breakfast"}
    ]
  }
}

Rules:
- Times must be 24-hour HH:MM (convert AM/PM if needed)
- Valid day keys: weekdays, monday, tuesday, wednesday, thursday, friday, saturday, sunday, weekend, default
- Use "weekdays" when Mon-Fri share the same schedule
- Use "default" when every day is the same
- Omit "presenter" and "description" if not visible in the image
- If multiple days are shown, include all of them as separate keys
- Return only the raw JSON object, nothing else"""


def parse_image_with_claude(image_bytes: bytes, media_type: str, api_key: str) -> dict[str, list[dict]]:
    """Send *image_bytes* to Claude and return a {day: [slot]} dict.

    Requires the ``anthropic`` package (``pip install anthropic``).
    Raises RuntimeError if the package is missing or the API key is invalid.
    """
    try:
        import anthropic
    except ImportError:
        raise RuntimeError(
            "The 'anthropic' package is not installed. "
            "Run: pip install anthropic"
        )

    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64.standard_b64encode(image_bytes).decode(),
                        },
                    },
                    {"type": "text", "text": _PROMPT},
                ],
            }
        ],
    )

    response_text = message.content[0].text.strip()

    # Strip markdown code fences if the model wrapped the JSON
    fence = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", response_text)
    if fence:
        response_text = fence.group(1)

    try:
        data = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Claude returned non-JSON response: {response_text[:200]}") from exc

    return data.get("days", {})
