import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from training.rewrite import serve


@pytest.fixture
def running():
    servers = []

    def start(generate):
        server = ThreadingHTTPServer(("127.0.0.1", 0), serve.make_handler(generate, "voxflow-rewrite"))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_address[1]}"

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def post(url, payload):
    data = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read())


def test_models_and_chat_completion(running):
    calls = []
    base = running(lambda messages, max_tokens: calls.append((messages, max_tokens)) or "整理后。")
    with urllib.request.urlopen(base + "/v1/models", timeout=5) as response:
        assert json.loads(response.read())["data"][0]["id"] == "voxflow-rewrite"
    messages = [{"role": "system", "content": "S"}, {"role": "user", "content": "额，你好"}]
    reply = post(base + "/v1/chat/completions", {"model": "x", "messages": messages, "max_tokens": 64})
    assert reply["choices"][0]["message"] == {"role": "assistant", "content": "整理后。"}
    assert calls == [(messages, 64)]
    post(base + "/v1/chat/completions", {"messages": messages, "max_tokens": 100000})
    assert calls[-1][1] == serve.MAX_NEW_TOKENS


def test_bad_requests_are_rejected(running):
    base = running(lambda messages, max_tokens: "x")
    for payload in (b"{broken", {"model": "x"}, {"messages": "hi"}):
        with pytest.raises(urllib.error.HTTPError) as caught:
            post(base + "/v1/chat/completions", payload)
        assert caught.value.code == 400
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(base + "/nope", timeout=5)
    assert caught.value.code == 404


def test_generation_errors_return_500(running):
    def broken(messages, max_tokens):
        raise RuntimeError("CUDA out of memory")

    base = running(broken)
    with pytest.raises(urllib.error.HTTPError) as caught:
        post(base + "/v1/chat/completions", {"messages": [{"role": "user", "content": "hi"}]})
    assert caught.value.code == 500
