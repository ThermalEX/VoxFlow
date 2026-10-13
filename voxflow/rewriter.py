"""Call a rewrite model through an OpenAI-compatible chat endpoint, and keep its settings."""

import json
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass

from PySide6.QtCore import QSettings

from .rewrite_prompts import CLEAN_SYSTEM_PROMPT, SUGGEST_SYSTEM_PROMPT

LOCAL_ENDPOINT = "http://127.0.0.1:8765/v1"
LOCAL_MODEL = "voxflow-rewrite"
CLEAN_TIMEOUT = 15
SUGGEST_TIMEOUT = 20
MAX_SUGGESTIONS = 3
MIN_ANSWER_TOKENS = 512
MAX_ANSWER_TOKENS = 4096
_REASONING = re.compile(r"<think>.*?</think>", re.S)


# New installs start with smart editing on so the local model loads with the app.
DEFAULT_ENABLED = True
# Version 1 stored "off" as the default; version 2 switches such settings on once.
DEFAULTS_VERSION = 2


def migrate_settings(settings: QSettings) -> None:
    if int(settings.value("rewrite/defaults_version", 1)) >= DEFAULTS_VERSION:
        return
    if DEFAULT_ENABLED and settings.contains("rewrite/enabled"):
        settings.setValue("rewrite/enabled", True)
    settings.setValue("rewrite/defaults_version", DEFAULTS_VERSION)


class RewriteError(Exception):
    """A failed rewrite; ``kind`` selects the user-facing explanation (see i18n ``error.*``)."""

    def __init__(self, message: str, kind: str = "other", code: int | None = None, path: str = "") -> None:
        super().__init__(message)
        self.kind = kind
        self.code = code
        self.path = path


@dataclass(frozen=True)
class RewriteConfig:
    enabled: bool = False
    provider: str = "local"
    endpoint: str = ""
    model: str = ""
    api_key: str = ""
    server_path: str = "runtime/llama.cpp/llama-server.exe"
    model_path: str = "training/rewrite/runs/qwen3.5-2b/gguf/voxflow-rewrite-q8_0.gguf"

    @property
    def base_url(self) -> str:
        return LOCAL_ENDPOINT if self.provider == "local" else self.endpoint.strip().rstrip("/")

    @property
    def model_name(self) -> str:
        return LOCAL_MODEL if self.provider == "local" else self.model.strip()

    @classmethod
    def from_settings(cls, settings: QSettings) -> "RewriteConfig":
        default = cls()
        values = {}
        fallbacks = asdict(default) | {"enabled": DEFAULT_ENABLED}
        for key, fallback in fallbacks.items():
            kind = bool if isinstance(fallback, bool) else str
            values[key] = settings.value(f"rewrite/{key}", fallback, type=kind)
        if values["provider"] not in {"local", "custom"}:
            values["provider"] = default.provider
        return cls(**values)

    def save(self, settings: QSettings) -> None:
        for key, value in asdict(self).items():
            settings.setValue(f"rewrite/{key}", value)
        settings.setValue("rewrite/defaults_version", DEFAULTS_VERSION)


class RewriteClient:
    def __init__(self, base_url: str, model: str, api_key: str = "", opener=urllib.request.urlopen) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self._open = opener

    def _request(self, path: str, payload: dict | None, timeout: float) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(self.base_url + path, data=data, headers=headers,
                                         method="POST" if payload is not None else "GET")
        try:
            with self._open(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RewriteError(str(exc), kind="http", code=exc.code) from exc
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            kind = "timeout" if isinstance(exc, TimeoutError) or isinstance(reason, TimeoutError) else "unreachable"
            raise RewriteError(str(exc) or type(exc).__name__, kind=kind) from exc
        except ValueError as exc:
            raise RewriteError(str(exc), kind="bad_response") from exc

    def _chat(self, system: str, text: str, timeout: float) -> str:
        reply = self._request("/chat/completions", {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": text}],
            # A rewrite can be as long as the dictation; Chinese is roughly one token per character.
            "max_tokens": min(MAX_ANSWER_TOKENS, max(MIN_ANSWER_TOKENS, 2 * len(text))),
            "temperature": 0,
        }, timeout)
        try:
            choice = reply["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RewriteError("unexpected response from the rewrite model", kind="bad_response") from exc
        if choice.get("finish_reason") == "length":
            raise RewriteError("the rewrite was cut off", kind="truncated")
        if isinstance(content, str):
            content = _REASONING.sub("", content).strip()
        if not isinstance(content, str) or not content:
            raise RewriteError("the rewrite model returned no text", kind="empty")
        return content

    def clean(self, text: str) -> str:
        return self._chat(CLEAN_SYSTEM_PROMPT, text, CLEAN_TIMEOUT)

    def suggest(self, text: str) -> list[dict]:
        content = self._chat(SUGGEST_SYSTEM_PROMPT, text, SUGGEST_TIMEOUT)
        start, end = content.find("["), content.rfind("]")
        if start == -1 or end < start:
            return []
        try:
            items = json.loads(content[start:end + 1])
        except ValueError:
            return []
        suggestions = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            label, body = item.get("label"), item.get("text")
            if (isinstance(label, str) and isinstance(body, str) and label.strip() and body.strip()
                    and body.strip() != text.strip()):
                suggestions.append({"label": label.strip(), "text": body.strip()})
        return suggestions[:MAX_SUGGESTIONS]

    def check(self, timeout: float = 3) -> str:
        reply = self._request("/models", None, timeout)
        models = reply.get("data") if isinstance(reply, dict) else None
        if models and isinstance(models[0], dict) and models[0].get("id"):
            return str(models[0]["id"])
        return "ok"
