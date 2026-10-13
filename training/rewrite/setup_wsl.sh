#!/usr/bin/env bash
# Create the WSL training environment for the rewrite model (Unsloth, transformers v5, CUDA PyTorch).
# Usage (inside WSL): bash training/rewrite/setup_wsl.sh
set -euo pipefail

ENV_DIR="${VOXFLOW_TRAIN_ENV:-$HOME/voxflow-train}"

if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

uv venv --python 3.12 "$ENV_DIR"
# shellcheck disable=SC1091
. "$ENV_DIR/bin/activate"
uv pip install unsloth sacrebleu
python - <<'PY'
import torch, transformers
print("torch", torch.__version__, "cuda", torch.cuda.is_available(), torch.cuda.get_device_name(0))
print("transformers", transformers.__version__)
PY
