from textwrap import dedent
import asyncio
import json
import os
from dotenv import load_dotenv
import aiohttp
import openai

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

ENABLE_AI_TAGS = True
BATCH_SIZE = 50
SKIP_TAGS = {"image", "video", "audio"}

def set_ai_enabled(enabled: bool):
    global ENABLE_AI_TAGS
    ENABLE_AI_TAGS = enabled
    print(f"AI tagging {'enabled' if enabled else 'disabled'}.")
def get_batched_ai_tags(file_names):
    if not ENABLE_AI_TAGS or not file_names:
        return {}

    prompt = dedent(f"""
        You will receive a list of 50 filenames.
        Return a JSON array where each object contains:
        - name: the filename
        - tags: a list of 2–5 descriptive tags (single words only)

        Example:
        [
          {{"name": "invoice_2023_q1.pdf", "tags": ["invoice", "finance", "Q1"]}},
          ...
        ]

        Filenames:
        {chr(10).join(file_names)}
    """)

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        content = response['choices'][0]['message']['content']

        print("\n🔍 AI RAW RESPONSE:\n")
        print(content[:1000])

        with open("openai_log.json", "a", encoding="utf-8") as f:
            f.write(content + "\n\n")

        parsed = json.loads(content)
        return {entry["name"].strip().lower(): ", ".join(entry["tags"]) for entry in parsed}
    except Exception as e:
        print(f"OpenAI error during batch tagging: {e}")
        return {}

async def async_get_batched_ai_tags(file_names):
    if not ENABLE_AI_TAGS or not file_names:
        return {}

    prompt = dedent(f"""
        You will receive a list of 50 filenames.
        Return a JSON array where each object contains:
        - name: the filename
        - tags: a list of 2–5 descriptive tags (single words only)

        Example:
        [
          {{"name": "invoice_2023_q1.pdf", "tags": ["invoice", "finance", "Q1"]}},
          ...
        ]

        Filenames:
        {chr(10).join(file_names)}
    """)

    headers = {
        "Authorization": f"Bearer {openai.api_key}",
        "Content-Type": "application/json"
    }

    body = {
        "model": "gpt-3.5-turbo",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("https://api.openai.com/v1/chat/completions", headers=headers, json=body) as resp:
                result = await resp.json()
                content = result['choices'][0]['message']['content']

                with open("openai_log.json", "a", encoding="utf-8") as f:
                    f.write(content + "\n\n")

                parsed = json.loads(content)
                return {entry["name"].strip().lower(): ", ".join(entry["tags"]) for entry in parsed}
    except Exception as e:
        print(f"[async] OpenAI error: {e}")
        return {}
