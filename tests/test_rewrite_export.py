from pathlib import Path

from training.rewrite import export_gguf


def test_conversion_commands_cover_each_requested_type():
    commands = export_gguf.conversion_commands(Path("/home/u/llama.cpp"), Path("/runs/merged"),
                                               Path("/runs/gguf"), ["q8_0", "bf16"])
    assert commands == [
        ["python", "/home/u/llama.cpp/convert_hf_to_gguf.py", "/runs/merged", "--outtype", "q8_0",
         "--outfile", "/runs/gguf/voxflow-rewrite-q8_0.gguf"],
        ["python", "/home/u/llama.cpp/convert_hf_to_gguf.py", "/runs/merged", "--outtype", "bf16",
         "--outfile", "/runs/gguf/voxflow-rewrite-bf16.gguf"],
    ]


def test_gguf_name_is_shared_with_the_app():
    assert export_gguf.gguf_name("q4_k_m") == "voxflow-rewrite-q4_k_m.gguf"
