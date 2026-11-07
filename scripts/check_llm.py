"""Check that your LLM settings work. Sends one tiny request.

Run:
    python scripts/check_llm.py

Reads LLM_BASE_URL, LLM_API_KEY and LLM_MODEL from .env. Never prints the key.
"""

import os
import sys

import openai
from dotenv import load_dotenv

load_dotenv()
base_url = os.getenv("LLM_BASE_URL")
api_key = os.getenv("LLM_API_KEY")
model = os.getenv("LLM_MODEL")

missing = [name for name, value in [("LLM_BASE_URL", base_url), ("LLM_API_KEY", api_key), ("LLM_MODEL", model)] if not value]
if missing:
    sys.exit(f"Missing in .env: {', '.join(missing)}. Copy .env.example to .env and fill them in.")

client = openai.OpenAI(base_url=base_url, api_key=api_key)

try:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Reply with the word OK only."}],
    )
except openai.AuthenticationError:
    sys.exit("Key rejected (401). Check you copied the full key into .env.")
except openai.PermissionDeniedError as e:
    sys.exit(f"Permission denied (403): {e.message}")
except openai.NotFoundError:
    sys.exit(f"Model or URL not found (404). Check LLM_MODEL={model} and LLM_BASE_URL.")
except openai.RateLimitError as e:
    sys.exit(f"Rate limit or quota reached (429): {e.message}")
except openai.BadRequestError as e:
    sys.exit(f"Bad request (400): {e.message}")
except openai.APIStatusError as e:
    sys.exit(f"API error {e.status_code}: {e.message}")
except openai.APIConnectionError:
    sys.exit(f"Cannot reach {base_url}. Check the URL and your internet.")

print(f"Model:  {response.model}")
print(f"Reply:  {(response.choices[0].message.content or '').strip()}")
if response.usage:
    print(f"Tokens: {response.usage.prompt_tokens} in, {response.usage.completion_tokens} out")
print("Your LLM settings work.")
