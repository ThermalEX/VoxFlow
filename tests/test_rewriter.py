import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from PySide6.QtCore import QSettings

from voxflow import rewriter
from voxflow.rewrite_prompts import CLEAN_SYSTEM_PROMPT, SUGGEST_SYSTEM_PROMPT


class FakeEndpoint:
    """Local OpenAI-compatible stand-in that records requests and replies per path."""

    def __init__(self):
        self.requests = []
        self.reply = {"content": "整理后。"}
        endpoint = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def _send(self, status, payload):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                endpoint.requests.append(("GET", self.path, dict(self.headers), None))
                self._send(200, {"object": "list", "data": [{"id": "voxflow-rewrite"}]})

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length))
                endpoint.requests.append(("POST", self.path, dict(self.headers), body))
                if "status" in endpoint.reply:
                    self._send(endpoint.reply["status"], {"error": "boom"})
                    return
                self._send(200, {"choices": [{"message": {"role": "assistant",
                                                          "content": endpoint.reply["content"]}}]})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def endpoint():
    fake = FakeEndpoint()
    yield fake
    fake.close()


def test_clean_posts_prompt_and_returns_text(endpoint):
    endpoint.reply = {"content": "  我明天请个假。\n"}
    client = rewriter.RewriteClient(endpoint.base_url, "voxflow-rewrite", api_key="secret")
    assert client.clean("额，我明天请个假啊") == "我明天请个假。"
    method, path, headers, body = endpoint.requests[-1]
    assert (method, path) == ("POST", "/v1/chat/completions")
    assert headers["Authorization"] == "Bearer secret"
    assert body["model"] == "voxflow-rewrite" and body["temperature"] == 0
    assert body["messages"] == [{"role": "system", "content": CLEAN_SYSTEM_PROMPT},
                                {"role": "user", "content": "额，我明天请个假啊"}]


def test_requests_without_key_send_no_authorization(endpoint):
    rewriter.RewriteClient(endpoint.base_url, "m").clean("你好")
    assert "Authorization" not in endpoint.requests[-1][2]


def test_suggest_parses_valid_items_only(endpoint):
    endpoint.reply = {"content": json.dumps([
        {"label": "更正式", "text": "本周五开会。"}, {"label": 3, "text": "x"},
        {"label": "原样", "text": "周五开会。"}, {"label": "空", "text": " "},
    ], ensure_ascii=False)}
    suggestions = rewriter.RewriteClient(endpoint.base_url, "m").suggest("周五开会。")
    assert suggestions == [{"label": "更正式", "text": "本周五开会。"}]
    assert endpoint.requests[-1][3]["messages"][0]["content"] == SUGGEST_SYSTEM_PROMPT


def test_suggest_tolerates_code_fences_and_garbage(endpoint):
    client = rewriter.RewriteClient(endpoint.base_url, "m")
    endpoint.reply = {"content": '好的：\n```json\n[{"label": "More formal", "text": "See you then."}]\n```'}
    assert client.suggest("see ya") == [{"label": "More formal", "text": "See you then."}]
    endpoint.reply = {"content": "抱歉，我无法提供建议。"}
    assert client.suggest("see ya") == []
    endpoint.reply = {"content": json.dumps([{"label": f"L{i}", "text": f"t{i}"} for i in range(5)])}
    assert len(client.suggest("see ya")) == 3


def test_errors_raise_rewrite_error(endpoint):
    client = rewriter.RewriteClient(endpoint.base_url, "m")
    endpoint.reply = {"status": 500}
    with pytest.raises(rewriter.RewriteError):
        client.clean("你好")
    endpoint.reply = {"content": "   "}
    with pytest.raises(rewriter.RewriteError):
        client.clean("你好")
    with pytest.raises(rewriter.RewriteError):
        rewriter.RewriteClient("http://127.0.0.1:9/v1", "m").clean("你好")

    def slow(*_args, **_kwargs):
        raise TimeoutError("timed out")

    with pytest.raises(rewriter.RewriteError):
        rewriter.RewriteClient(endpoint.base_url, "m", opener=slow).clean("你好")


def test_check_lists_models(endpoint):
    assert rewriter.RewriteClient(endpoint.base_url, "m").check() == "voxflow-rewrite"
    assert endpoint.requests[-1][:2] == ("GET", "/v1/models")


def test_config_round_trip_and_local_defaults(tmp_path):
    settings = QSettings(str(tmp_path / "rewrite.ini"), QSettings.Format.IniFormat)
    default = rewriter.RewriteConfig.from_settings(settings)
    assert not default.enabled and default.provider == "local"
    assert default.base_url == rewriter.LOCAL_ENDPOINT and default.model_name == rewriter.LOCAL_MODEL
    custom = rewriter.RewriteConfig(enabled=True, provider="custom", endpoint="http://host:1234/v1/",
                                    model="qwen", api_key="k")
    custom.save(settings)
    loaded = rewriter.RewriteConfig.from_settings(settings)
    assert loaded == custom
    assert loaded.base_url == "http://host:1234/v1" and loaded.model_name == "qwen"
