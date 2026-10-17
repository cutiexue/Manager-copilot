"""Load provider configuration without third-party dependencies."""
import os
import re
from pathlib import Path
from dataclasses import dataclass, field
from urllib.parse import urlsplit

@dataclass(frozen=True)
class LLMConfig:
    provider: str
    model: str
    base_url: str
    api_key: str = field(repr=False)

def read_env(path):
    try:
        source = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeError):
        raise ValueError("Cannot read project .env as UTF-8.") from None
    values = {}
    for number, line in enumerate(source.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError(f"Invalid .env assignment on line {number}.")
        if value.startswith(('"', "'")):
            end = value.find(value[0], 1)
            if end < 0 or (value[end+1:].strip() and not value[end+1:].strip().startswith("#")):
                raise ValueError(f"Invalid .env quote on line {number}.")
            value = value[1:end]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        values[key] = value
    return values

def load_config(provider=None):
    values = read_env(Path(__file__).resolve().with_name(".env"))
    values.update(os.environ)
    provider = (provider if provider is not None else values.get("LLM_PROVIDER", "deepseek")).strip().lower()
    defaults = {
        "openai": ("gpt-4.1-mini", "https://api.openai.com/v1"),
        "deepseek": ("deepseek-flash", "https://api.deepseek.com"),
    }
    if provider not in defaults:
        raise ValueError("LLM_PROVIDER must be openai or deepseek.")
    prefix = provider.upper()
    model, base_url = defaults[provider]
    model = values.get(prefix + "_MODEL", model).strip()
    base_url = values.get(prefix + "_BASE_URL", base_url).strip().rstrip("/")
    url = urlsplit(base_url)
    if not model:
        raise ValueError(f"{prefix}_MODEL cannot be empty.")
    if url.scheme != "https" or not url.netloc or url.username or url.password or url.query or url.fragment:
        raise ValueError(f"{prefix}_BASE_URL must be an HTTPS API base URL.")
    return LLMConfig(provider, model, base_url, values.get(prefix + "_API_KEY", "").strip())
