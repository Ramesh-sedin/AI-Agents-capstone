"""One-line-style Gemini key verification script."""

import os
import sys

from dotenv import load_dotenv
from google import genai

load_dotenv()

if not os.getenv("GEMINI_API_KEY"):
    print("Set GEMINI_API_KEY in .env or in your shell before running this script.", file=sys.stderr)
    raise SystemExit(1)

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
response = client.models.generate_content(
    model="gemini-3.5-flash",
    contents="Reply with exactly: Gemini API key works",
)
print(response.text)
