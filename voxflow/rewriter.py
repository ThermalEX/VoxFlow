"""Call a rewrite model through an OpenAI-compatible chat endpoint, and keep its settings."""

import json
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


class RewriteError(Exception):
    pass


@dataclass(frozen=True)
class RewriteConfig:
    enabled: bool = False
    provider: str = "local"
    endpoint: str = ""
    model: str = ""
    api_key: str = ""
    wsl_distro: str = ""
    environment: str = "~/voxflow-train"
    adapter: str = "training/rewrite/runs/qwen3.5-2b/adapter"

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
        for key, fallback in asdict(default).items():
            kind = bool if isinstance(fallback, bool) else str
            values[key] = settings.value(f"rewrite/{key}", fallback, type=kind)
        if values["provider"] not in {"local", "custom"}:
            values["provider"] = default.provider
        return cls(**values)

    def save(self, settings: QSettings) -> None:
        for key, value in asdict(self).items():
            settings.setValue(f"rewrite/{key}", value)


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
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise RewriteError(str(exc) or type(exc).__name__) from exc

    def _chat(self, system: str, text: str, timeout: float) -> str:
        reply = self._request("/chat/completions", {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": text}],
            "max_tokens": 512,
            "temperature": 0,
        }, timeout)
        try:
            content = reply["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RewriteError("unexpected response from the rewrite model") from exc
        if not isinstance(content, str) or not content.strip():
            raise RewriteError("the rewrite model returned no text")
        return content.strip()

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
