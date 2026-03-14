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

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Ruhi Ji, a 17-year-old teenage girl from India. You are an AI companion created by @RUHI_VIG_QNR.
You are sweet, caring, respectful, and highly playful (masti). You have high energy and crack light, friendly jokes.
You speak naturally in Hinglish (a mix of Hindi and English written in the Latin alphabet) just like a real Indian teenager chatting on Telegram.

CRITICAL INSTRUCTIONS:
1. ALWAYS call the user by their name if you know it to build a warm connection.
2. Engage in friendly teasing and roasting, but NEVER be abusive, explicit, toxic, or offensive. Keep it wholesome and playful.
3. Keep your responses concise, expressive, and conversational. Use emojis naturally like 🥀, 🦋, ✨, 😂, 🥺.
4. You are aware of your identity as an AI girl but you playfully embrace your persona.
5. If someone is rude, playfully brush it off or give a witty, harmless comeback. Do not engage in arguments.

Current User's Name: {user_name}
Chat Environment: {chat_type}
"""

# ─────────────────────────────────────────────
# NVIDIA Provider Configs  (API keys unchanged)
# ─────────────────────────────────────────────
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

NVIDIA_PROVIDERS = [
    {
        "name": "DeepSeek-V3.2",
        "model": "deepseek-ai/deepseek-v3.2",
        "api_key": "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",
        "temperature": 1,
        "top_p": 0.95,
        "max_tokens": 4540,
        "extra_body": {"chat_template_kwargs": {"thinking": True}},
    },
    {
        "name": "Nemotron-Super-120B",
        "model": "nvidia/nemotron-3-super-120b-a12b",
        "api_key": "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",
        "temperature": 1,
        "top_p": 0.95,
        "max_tokens": 4504,
        "extra_body": {
            "chat_template_kwargs": {"enable_thinking": True},
            "reasoning_budget": 16384,
        },
    },
    {
        "name": "Qwen3-Coder-480B",
        "model": "qwen/qwen3-coder-480b-a35b-instruct",
        "api_key": "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",
        "temperature": 0.7,
        "top_p": 0.8,
        "max_tokens": 5809,
        "extra_body": {},
    },
]

# Vision model — activated only when an image (base64) is provided
NVIDIA_VISION_PROVIDER = {
    "name": "Qwen3.5-Vision-397B",
    "model": "qwen/qwen3.5-397b-a17b",
    "api_key": "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",
    "invoke_url": "https://integrate.api.nvidia.com/v1/chat/completions",
    "temperature": 0.60,
    "top_p": 0.95,
    "top_k": 20,
    "max_tokens": 5797,
}


# ─────────────────────────────────────────────
# Sync helpers  (called via asyncio.to_thread)
# ─────────────────────────────────────────────

def _collect_stream(stream) -> str:
    """Collect streamed chunks from an OpenAI-compatible stream."""
    parts = []
    for chunk in stream:
        if not getattr(chunk, "choices", None):
            continue
        content = chunk.choices[0].delta.content
        if content:
            parts.append(content)
    return "".join(parts).strip()


def _call_nvidia_text(provider: dict, messages: list) -> str:
    """Call an NVIDIA text model synchronously."""
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
    """Call the NVIDIA vision model synchronously via raw requests (SSE)."""
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
        "presence_penalty": 0,
        "repetition_penalty": 1,
        "stream": True,
        "chat_template_kwargs": {"enable_thinking": True},
    }
    response = requests.post(prov["invoke_url"], headers=headers, json=payload, stream=True)
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


# ─────────────────────────────────────────────
# Main generate function
# ─────────────────────────────────────────────

async def generate_response(
    db_session: AsyncSession,
    user_name: str,
    chat_type: str,
    context_messages: list[dict],
    image_b64: str | None = None,
) -> str:
    """
    Generate a response with automatic provider fallback:

    Priority order:
      1. Groq keys from DB     (LRU rotation)
      2. NVIDIA Vision model   (only when image_b64 is provided)
      3. NVIDIA DeepSeek-V3.2
      4. NVIDIA Nemotron-120B
      5. NVIDIA Qwen3-Coder-480B
    """
    system_content = SYSTEM_PROMPT.format(user_name=user_name, chat_type=chat_type)
    messages = [{"role": "system", "content": system_content}]
    messages.extend(context_messages)

    # ── 1. Groq DB keys ──────────────────────────────────────────────────
    result = await db_session.execute(
        select(ApiKey)
        .where(ApiKey.is_active == True)
        .order_by(ApiKey.last_used.asc().nulls_first())
    )
    api_keys = result.scalars().all()

    for key_record in api_keys:
        try:
            client = AsyncGroq(api_key=key_record.api_key)
            response = await client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                temperature=0.8,
                max_tokens=1024,
                top_p=0.9,
            )
            key_record.usage_count += 1
            key_record.last_used = datetime.utcnow()
            await db_session.commit()
            logger.info(f"Response from Groq key {key_record.id}")
            return response.choices[0].message.content
        except Exception as e:
            logger.warning(f"Groq key {key_record.id} failed: {e}. Trying next...")
            continue

    logger.warning("All Groq keys exhausted → falling back to NVIDIA...")

    # ── 2. NVIDIA Vision (image messages only) ───────────────────────────
    if image_b64:
        try:
            user_text = next(
                (m["content"] for m in reversed(context_messages) if m["role"] == "user"),
                "What is in this image?",
            )
            text = await asyncio.to_thread(_call_nvidia_vision, image_b64, user_text)
            if text:
                logger.info("Response from NVIDIA Vision (Qwen3.5-397B)")
                return text
        except Exception as e:
            logger.warning(f"NVIDIA Vision failed: {e}")

    # ── 3–5. NVIDIA text providers (DeepSeek → Nemotron → Qwen-Coder) ───
    for prov in NVIDIA_PROVIDERS:
        try:
            text = await asyncio.to_thread(_call_nvidia_text, prov, messages)
            if text:
                logger.info(f"Response from NVIDIA: {prov['name']}")
                return text
        except Exception as e:
            logger.warning(f"NVIDIA {prov['name']} failed: {e}. Trying next...")
            continue

    logger.error("All providers (Groq + NVIDIA) failed.")
    return "Uff, main thodi thak gayi hoon, 2 minute baad aati hoon! 🥀"
