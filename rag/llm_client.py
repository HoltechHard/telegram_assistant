import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# get the project root
BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

KIMI_API_KEY = os.getenv("KIMI_API_KEY")
KIMI_BASE_URL = os.getenv("KIMI_BASE_URL")

# Initialize GLM client
client = OpenAI(
    api_key=KIMI_API_KEY,
    base_url=KIMI_BASE_URL
)

def load_system_prompt():
    prompt_path = BASE_DIR / "rag/instruct.md"

    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()

def query_llm(user_message: str):
    system_prompt = load_system_prompt()

    response = client.chat.completions.create(
        model="moonshotai/kimi-k2.5",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        temperature=0.2,
        max_tokens=1024
    )

    return response.choices[0].message.content
