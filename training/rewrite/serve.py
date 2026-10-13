"""Serve the fine-tuned rewrite model behind a minimal OpenAI-compatible API (run inside the WSL training env).

Usage: python -m training.rewrite.serve --adapter training/rewrite/runs/qwen3.5-2b/adapter --port 8765
The server exits when its stdin closes, so VoxFlow can stop it by closing the pipe.
"""

import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

MAX_NEW_TOKENS = 512
DEFAULT_NEW_TOKENS = 384


def make_handler(generate: Callable[[list[dict], int], str], model_name: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            print(f"{self.address_string()} {format % args}", file=sys.stderr, flush=True)

        def _send(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _error(self, status: int, message: str) -> None:
            self._send(status, {"error": {"message": message}})

        def do_GET(self) -> None:
            if self.path.rstrip("/") != "/v1/models":
                self._error(404, "not found")
                return
            self._send(200, {"object": "list", "data": [{"id": model_name, "object": "model"}]})

        def do_POST(self) -> None:
            if self.path.rstrip("/") != "/v1/chat/completions":
                self._error(404, "not found")
                return
            try:
                request = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                messages = request["messages"]
                if not isinstance(messages, list) or not all(isinstance(m, dict) for m in messages):
                    raise ValueError("messages must be a list of objects")
                max_tokens = min(int(request.get("max_tokens") or DEFAULT_NEW_TOKENS), MAX_NEW_TOKENS)
            except (ValueError, KeyError, TypeError) as exc:
                self._error(400, f"bad request: {exc}")
                return
            try:
                content = generate(messages, max_tokens)
            except Exception as exc:  # report model failures to the client instead of dropping the socket
                self._error(500, str(exc))
                return
            self._send(200, {
                "id": f"chatcmpl-{time.time_ns()}",
                "object": "chat.completion",
                "model": model_name,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                             "finish_reason": "stop"}],
            })

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenAI-compatible server for the VoxFlow rewrite model")
    parser.add_argument("--model", default="Qwen/Qwen3.5-2B")
    parser.add_argument("--adapter", help="LoRA adapter directory; omit to serve the base model")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--name", default="voxflow-rewrite")
    args = parser.parse_args()

    from unsloth import FastLanguageModel  # must be imported before transformers
    import torch

    from .train import render_prompt

    model, processor = FastLanguageModel.from_pretrained(
        model_name=args.adapter or args.model, max_seq_length=2048, load_in_4bit=False, load_in_16bit=True)
    tokenizer = getattr(processor, "tokenizer", processor)
    FastLanguageModel.for_inference(model)
    lock = threading.Lock()

    def generate(messages: list[dict], max_tokens: int) -> str:
        with lock, torch.inference_mode():
            inputs = tokenizer(render_prompt(tokenizer, messages), return_tensors="pt",
                               add_special_tokens=False).to(model.device)
            output = model.generate(**inputs, max_new_tokens=max_tokens, do_sample=False)
            text = tokenizer.decode(output[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
        return text.replace("<think>", "").replace("</think>", "").strip()

    generate([{"role": "system", "content": "warm up"}, {"role": "user", "content": "你好"}], 8)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(generate, args.name))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print("READY", flush=True)
    sys.stdin.read()  # EOF means the parent (VoxFlow) went away
    server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
