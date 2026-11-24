# VoxFlow · local voice input with checkable AI edits

*README prose word count: about 1,000 words (code and commands excluded).*

VoxFlow is a Windows voice-input tool. You press a hotkey and speak; a local speech recogniser shows a live draft; when you stop, a small fine-tuned language model removes fillers and applies spoken corrections and instructions ("Wednesday, no, Thursday", "make it more formal"). The edit is always shown and reversible, and nothing is typed into the target app until you press Enter. It is the prototype for my Intelligent Interactive Systems project on steering and checking AI edits to dictated text.

## Project status

**Works (implemented)**

- Dictation overlay: hotkey `Ctrl+Shift+Space`, live draft, editable result, paste back into the previously focused app; `Continue` adds more speech to the current text.
- Smart editing with a local model: one strike-and-fade edit animation, `Undo edits` with a hover preview of what was said, 0–3 suggestion buttons. Any model failure keeps the original text.
- Review mode (Settings › Smart editing › *Review edits before applying*, off by default): every edit stays marked in place and can be kept or turned back individually.
- Memory (off by default): "remember …" requests, background extraction of names, terms and events, pinyin-based correction of misheard names, "Fill from memory" suggestions, daily summaries; a settings page to inspect, edit, delete and set retention (7 days or forever).
- Chinese/English interface, first-run tutorial, in-app model downloads with checksum verification, Windows installer.
- Fine-tuning and evaluation pipeline for the rewrite model (`training/rewrite/`), with fixed test sets.

**Simulated**

- Evaluation uses fixed, hand-written test sets replayed through the model; no participants have used VoxFlow yet.

**Unfinished / planned**

- Logging which edits people keep or reject in review mode, and a small pilot comparing immediate edits with review mode.
- Real-recording comparison of the speech recogniser with newer candidates (e.g. Qwen3-ASR).
- Not validated by hand on every set-up: multi-monitor/high-DPI layouts and pasting into every kind of app.

## Technology stack

| Part | Technology | Role |
| --- | --- | --- |
| Interface | Python 3.12, PySide6 (Qt) | Overlay, settings, tray, animations |
| Audio | sounddevice | Microphone capture; audio stays in memory |
| Speech recognition (AI) | SenseVoiceSmall INT8 via sherpa-onnx, in a worker process | Live draft and final transcript, Chinese/English/Japanese/Korean/Cantonese |
| Rewrite model (AI) | Qwen3.5-2B + LoRA ("VoxFlow-rewrite" v6), GGUF Q8, served by llama.cpp `llama-server` (Vulkan) | Clean, suggest, memory extract / fill / summary |
| Rules around the model | Python (`memory_dates.py`, `memory_names.py` with pypinyin, `memory_command.py`) | Dates, name correction, "remember" detection, output checks |
| Memory | SQLite (standard library) | Local store, only when memory is on |
| Training | Unsloth + PEFT LoRA in WSL; llama.cpp tools for GGUF export | Not needed to run the app |
| Packaging | PyInstaller, Inno Setup | Installer |

Undecided: whether to switch the speech recogniser (needs a real-recording benchmark) and whether to move to a larger base model once one fits a 6 GB GPU.

## Running or inspecting the work

Windows 10/11 with Python 3.12. A GPU is optional for the rewrite model (any Vulkan GPU; CPU works but is slow).

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe scripts\download_model.py   # speech model (~240 MB) into models/
.\.venv\Scripts\python.exe -m voxflow                  # start; the tutorial offers llama.cpp and the rewrite model
```

- **Without a microphone:** `.\.venv\Scripts\python.exe -m voxflow --file path\to\speech.wav` transcribes one file.
- **Tests (452, no microphone or model needed):** `$env:QT_QPA_PLATFORM='offscreen'; .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider`. The review mode is covered by `tests/test_window_review.py`.
- **Replay the storyboards with the real model:** see the commands at the top of [docs/a2/scripts/capture.py](docs/a2/scripts/capture.py); model outputs and latencies of the submitted run are in [docs/a2/capture_log.json](docs/a2/capture_log.json).
- **Model evaluation:** start `llama-server` on port 8765, then `.\.venv\Scripts\python.exe -m training.rewrite.evaluate --endpoint http://127.0.0.1:8765/v1 --output training/rewrite/runs/<name>`. Results and their test-set versions are recorded in [docs/research-log.md](docs/research-log.md) (Chinese).
- **Using an online model instead:** Settings › Smart editing › Model source › *OpenAI-compatible service*; enter your own endpoint and key. No key is stored in this repository; keys are kept in your Windows user settings.
- **Installer build:** `.\.venv\Scripts\python.exe packaging\build.py` (needs `pip install -e ".[build]"` and Inno Setup).

## Development record

Links point to commits on GitHub. The full experiment history, including failed attempts, is in [docs/research-log.md](docs/research-log.md).

| Stage | What changed and why | What I checked |
| --- | --- | --- |
| 1. Local dictation (6–7 Oct) | Overlay, worker-process ASR and paste-back ([f86dec1](https://github.com/ThermalEX/VoxFlow/commit/f86dec1)); an empty final result no longer erases the live draft ([2f085c3](https://github.com/ThermalEX/VoxFlow/commit/2f085c3)). | Unit tests for scheduler, buffer and session isolation; microphone smoke script. |
| 2. Rewrite model (13–15 Oct) | Hand-written seed data and a fixed test set ([14a6813](https://github.com/ThermalEX/VoxFlow/commit/14a6813)); LoRA fitted into 6 GB ([c644f3b](https://github.com/ThermalEX/VoxFlow/commit/c644f3b)); v4 targeted the sentences the model over-edited ([31a9748](https://github.com/ThermalEX/VoxFlow/commit/31a9748)). | Instruction residue 35% → 0% and unchanged-sentence preservation 80% → 95% on the same test set. |
| 3. Showing the edit (13 Oct) | Diff-based edit animation and undo instead of silently replacing text ([ff78323](https://github.com/ThermalEX/VoxFlow/commit/ff78323), [2f78a89](https://github.com/ThermalEX/VoxFlow/commit/2f78a89)). | Window tests for animation, undo, hover preview and stale results. |
| 4. Latency (13 Oct) | Native `llama-server` instead of a Python model in WSL ([32c4073](https://github.com/ThermalEX/VoxFlow/commit/32c4073)), because 1.1 s per sentence felt like waiting. | Median 0.14 s per sentence, quality unchanged. |
| 5. Usable by others (14–18 Oct) | Bilingual UI ([184c8f2](https://github.com/ThermalEX/VoxFlow/commit/184c8f2)), Continue ([e1f6a10](https://github.com/ThermalEX/VoxFlow/commit/e1f6a10)), installer ([ac95e76](https://github.com/ThermalEX/VoxFlow/commit/ac95e76)), verified downloads ([4d4f945](https://github.com/ThermalEX/VoxFlow/commit/4d4f945)), tutorial ([3e84aef](https://github.com/ThermalEX/VoxFlow/commit/3e84aef)). | Tests for resumable downloads, checksums and the tutorial. |
| 6. Rejected directions (18–19 Oct) | v5 data was reverted after it got worse ([8455631](https://github.com/ThermalEX/VoxFlow/commit/8455631)); a Gemma 4 E2B base was tried and stopped ([5fe9b3a](https://github.com/ThermalEX/VoxFlow/commit/5fe9b3a)). | Same test set for every comparison. |
| 7. Memory (20–21 Oct) | Memory store, settings page and fill-in suggestions ([bb2e259](https://github.com/ThermalEX/VoxFlow/commit/bb2e259), [70a15f7](https://github.com/ThermalEX/VoxFlow/commit/70a15f7)); dates computed by rules because the model got them wrong ([657e818](https://github.com/ThermalEX/VoxFlow/commit/657e818)); v6 model ([649b386](https://github.com/ThermalEX/VoxFlow/commit/649b386)). | Memory evaluation set: event-time correctness 31% → 54% once dates moved to rules; v6 extraction recall 94%. |
| 8. Review mode (17 Nov) | Per-edit keep/reject, the comparison condition proposed in my literature review ([c3a3ddb](https://github.com/ThermalEX/VoxFlow/commit/c3a3ddb)); spacing-only changes no longer count as decisions ([bc882dd](https://github.com/ThermalEX/VoxFlow/commit/bc882dd)). | 17 new tests; storyboards captured with the real model. |

## AI assistance

I used AI assistance in two ways, through Claude Code (Anthropic, model Claude Opus 5.5). For the software, it helped write the programs and code, including tests, training data, evaluation scripts and the scripts that draw the figures. For the writing, it helped draft this README and the report and translate them from Chinese into English, correcting grammar and wording. I set the goals and design decisions, ran the tests and the app to check the code, and dropped changes that did not hold up; for example, the v5 data and the Gemma base model were abandoned after evaluation.

## Additional files

- [docs/a2/](docs/a2/): storyboards, system diagram (PNG and SVG) and the scripts that generate them.
- [docs/research-log.md](docs/research-log.md): experiments, results by test-set version, problems and fixes (Chinese).
- [HANDOFF.md](HANDOFF.md): code structure and developer notes (Chinese).
- Models are not in Git; they download from [Hugging Face](https://huggingface.co/ThermalEX/voxflow-rewrite) inside the app or via `scripts/download_model.py`.
