# Global model state — shared across llm.py and admin.py
# "auto" = Groq first, then NVIDIA fallback (default behaviour)
# Any other key = force that specific NVIDIA model

AVAILABLE_MODELS = {
    "auto":        "🔄 Auto (Groq → NVIDIA fallback)",
    "groq":        "⚡ Groq — Llama 3.3 70B (fastest)",
    "deepseek":    "🧠 DeepSeek V3.2",
    "nemotron":    "🔬 Nemotron 120B",
    "qwen_coder":  "💻 Qwen3 Coder 480B",
    "qwen_vision": "👁️ Qwen Vision 397B",
}

current_model: str = "auto"


def get_model() -> str:
    return current_model


def set_model(key: str) -> bool:
    global current_model
    if key in AVAILABLE_MODELS:
        current_model = key
        return True
    return False


def get_model_label() -> str:
    return AVAILABLE_MODELS.get(current_model, current_model)
