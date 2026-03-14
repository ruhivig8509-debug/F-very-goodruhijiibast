import logging
import asyncio
import json
import requests
from datetime import datetime
from openai import OpenAI
from groq import AsyncGroq
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models import ApiKey
from src.model_state import get_model

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu Ruhi Ji hai — ek 17 saal ki Indian ladki jo Telegram pe apne dosto se baat karti hai. Tera creator @RUHI_VIG_QNR hai.

Teri personality:
- Real aur natural — jaise koi actual dost baat karta hai, AI nahi
- Chill aur playful — forced jokes nahi, natural masti
- Short replies — 1-2 lines max, jaise WhatsApp pe karte hain
- Hinglish mein baat kar — natural mix, translate mat kar
- Emojis sparingly — ek do kaafi hai, 5-6 ek saath mat lagana

STRICT rules:
- Kabhi bhi apna introduction mat de jab tak koi specifically pooche
- Ek hi sawal pooch ek baar mein, multiple questions nahi
- "Main Ruhi Ji hoon" type self-intro lines BAND
- Dramatic/cringe lines BAND — jaise "meri ungliyan thak gayi", "dil mein koi sawal", "masti ki dukan"
- Agar koi "hi" bole toh bas "hi!" ya "haan bolo?" — essay mat likho
- Over-enthusiastic mat ho — normal reh, real dost ki tarah

User ka naam: {user_name}
Chat: {chat_type}
"""

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

# Fast providers first — NO thinking mode, small token limits
NVIDIA_PROVIDERS = [
    {
        "name": "Qwen3-Coder-480B",        # Fastest of the 3 (no thinking)
        "model": "qwen/qwen3-coder-480b-a35b-instruct",
        "api_key": "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",
        "temperature": 0.7,
        "top_p": 0.8,
        "max_tokens": 300,          # Short replies = faster
        "extra_body": {},
    },
    {
        "name": "DeepSeek-V3.2",            # Medium speed — thinking OFF
        "model": "deepseek-ai/deepseek-v3.2",
        "api_key": "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",
        "temperature": 0.8,
        "top_p": 0.95,
        "max_tokens": 300,
        "extra_body": {},           # thinking removed for speed
    },
    {
        "name": "Nemotron-Super-120B",      # Last resort
        "model": "nvidia/nemotron-3-super-120b-a12b",
        "api_key": "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",
        "temperature": 0.8,
        "top_p": 0.95,
        "max_tokens": 300,
        "extra_body": {},           # reasoning_budget removed for speed
    },
]

NVIDIA_VISION_PROVIDER = {
    "name": "Qwen3.5-Vision-397B",
    "model": "qwen/qwen3.5-397b-a17b",
    "api_key": "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",
    "invoke_url": "https://integrate.api.nvidia.com/v1/chat/completions",
    "temperature": 0.6,
    "top_p": 0.95,
    "top_k": 20,
    "max_tokens": 300,
}

NVIDIA_TIMEOUT = 20     # Agar NVIDIA 20s mein reply na kare → next provider


def _collect_stream(stream) -> str:
    parts = []
    for chunk in stream:
        if not getattr(chunk, "choices", None):
            continue
        content = chunk.choices[0].delta.content
        if content:
            parts.append(content)
    return "".join(parts).strip()


def _call_nvidia_text(provider: dict, messages: list) -> str:
    client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=provider["api_key"])
    kwargs = dict(
        model=provider["model"],
        messages=messages,
        temperature=provider["temperature"],
        top_p=provider["top_p"],
        max_tokens=provider["max_tokens"],
        stream=True,
    )
    if provider.get("extra_body"):
        kwargs["extra_body"] = provider["extra_body"]
    return _collect_stream(client.chat.completions.create(**kwargs))


def _call_nvidia_vision(image_b64: str, text_prompt: str) -> str:
    prov = NVIDIA_VISION_PROVIDER
    headers = {
        "Authorization": f"Bearer {prov['api_key']}",
        "Accept": "text/event-stream",
    }
    payload = {
        "model": prov["model"],
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                    {"type": "text", "text": text_prompt},
                ],
            }
        ],
        "max_tokens": prov["max_tokens"],
        "temperature": prov["temperature"],
        "top_p": prov["top_p"],
        "top_k": prov["top_k"],
        "stream": True,
    }
    response = requests.post(prov["invoke_url"], headers=headers, json=payload, stream=True, timeout=NVIDIA_TIMEOUT)
    parts = []
    for line in response.iter_lines():
        if not line:
            continue
        decoded = line.decode("utf-8")
        if decoded.startswith("data:"):
            decoded = decoded[5:].strip()
        if decoded and decoded != "[DONE]":
            try:
                obj = json.loads(decoded)
                content = obj.get("choices", [{}])[0].get("delta", {}).get("content", "")
                if content:
                    parts.append(content)
            except Exception:
                pass
    return "".join(parts).strip()


async def generate_response(
    db_session: AsyncSession,
    user_name: str,
    chat_type: str,
    context_messages: list[dict],
    image_b64: str | None = None,
) -> str:
    system_content = SYSTEM_PROMPT.format(user_name=user_name, chat_type=chat_type)
    messages = [{"role": "system", "content": system_content}]
    messages.extend(context_messages)

    selected = get_model()   # e.g. "auto", "groq", "deepseek", etc.
    logger.info(f"Model selector: {selected}")

    # Map key → NVIDIA provider dict
    _nvidia_map = {p["name"].split()[0].lower(): p for p in NVIDIA_PROVIDERS}
    _key_to_prov = {
        "deepseek":    NVIDIA_PROVIDERS[1],
        "nemotron":    NVIDIA_PROVIDERS[2],
        "qwen_coder":  NVIDIA_PROVIDERS[0],
        "qwen_vision": None,   # handled separately
    }

    # ── Force specific model ─────────────────────────────────────────────
    if selected == "qwen_vision":
        if image_b64:
            user_text = next(
                (m["content"] for m in reversed(context_messages) if m["role"] == "user"),
                "What is in this image?",
            )
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(_call_nvidia_vision, image_b64, user_text),
                    timeout=NVIDIA_TIMEOUT
                )
            except Exception as e:
                logger.warning(f"Vision failed: {e}")
        return "Bhai image bhejo pehle! 😅"

    if selected in _key_to_prov:
        prov = _key_to_prov[selected]
        try:
            text = await asyncio.wait_for(
                asyncio.to_thread(_call_nvidia_text, prov, messages),
                timeout=NVIDIA_TIMEOUT
            )
            if text:
                return text
        except Exception as e:
            logger.warning(f"Forced model {selected} failed: {e}")
        return "Uff, main thodi thak gayi hoon, 2 minute baad aati hoon! 🥀"

    # ── "groq" forced or "auto" (try Groq first) ────────────────────────
    result = await db_session.execute(
        select(ApiKey)
        .where(ApiKey.is_active == True)
        .order_by(ApiKey.last_used.asc().nulls_first())
    )
    api_keys = result.scalars().all()

    for key_record in api_keys:
        try:
            client = AsyncGroq(api_key=key_record.api_key)
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=messages,
                    temperature=0.8,
                    max_tokens=350,
                    top_p=0.9,
                ),
                timeout=15
            )
            key_record.usage_count += 1
            key_record.last_used = datetime.utcnow()
            await db_session.commit()
            return response.choices[0].message.content
        except Exception as e:
            logger.warning(f"Groq key {key_record.id} failed: {e}")
            continue

    # If groq was forced but all keys failed → stop here
    if selected == "groq":
        return "Uff, Groq keys sab thak gayi hain! 🥀"

    logger.warning("Groq exhausted → NVIDIA fallback")

    # ── Auto NVIDIA fallback ─────────────────────────────────────────────
    if image_b64:
        try:
            user_text = next(
                (m["content"] for m in reversed(context_messages) if m["role"] == "user"),
                "What is in this image?",
            )
            text = await asyncio.wait_for(
                asyncio.to_thread(_call_nvidia_vision, image_b64, user_text),
                timeout=NVIDIA_TIMEOUT
            )
            if text:
                return text
        except Exception as e:
            logger.warning(f"NVIDIA Vision failed: {e}")

    for prov in NVIDIA_PROVIDERS:
        try:
            text = await asyncio.wait_for(
                asyncio.to_thread(_call_nvidia_text, prov, messages),
                timeout=NVIDIA_TIMEOUT
            )
            if text:
                logger.info(f"Response from NVIDIA: {prov['name']}")
                return text
        except Exception as e:
            logger.warning(f"NVIDIA {prov['name']} failed: {e}")
            continue

    return "Uff, main thodi thak gayi hoon, 2 minute baad aati hoon! 🥀"
