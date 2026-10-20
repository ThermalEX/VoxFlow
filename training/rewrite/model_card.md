---
license: apache-2.0
base_model: Qwen/Qwen3.5-2B
language:
  - zh
  - en
pipeline_tag: text-generation
library_name: gguf
tags:
  - gguf
  - llama.cpp
  - speech-to-text
  - text-rewriting
  - voice-input
---

# VoxFlow Rewrite

A 2B model that turns raw speech-recognition text into the text you meant to type: it removes fillers, applies spoken self-corrections ("Friday, no, Saturday"), follows inline voice commands ("translate to English", "make it more polite") and suggests up to three rewrites. Fine-tuned from Qwen3.5-2B with LoRA and exported to GGUF for [llama.cpp](https://github.com/ggml-org/llama.cpp). It is the local smart-editing model of [VoxFlow](https://github.com/ThermalEX/VoxFlow), a Windows voice-input app.

---

VoxFlow 的本地智能编辑模型：把语音识别得到的口语原文，整理成真正想输入的文字。基于 Qwen3.5-2B 做 LoRA 微调，导出为 GGUF，在 6 GB 显存的笔记本上单句约 0.14 秒。

## 能做什么

模型有两个任务，用不同的系统提示区分：

**任务 1：清理并执行语音指令**，输出最终文字。

| 输入（语音识别原文） | 输出 |
| --- | --- |
| 额，那个，明天下午三点开会，不对，四点 | 明天下午四点开会。 |
| 我今天要买苹果，梨子，哦昨天买过苹果了，去掉苹果 | 我今天要买梨子。 |
| 国庆去爷爷家，爷爷说他来我们这儿，那就在我们这儿过 | 国庆在我们这儿过。 |
| 你们物流太慢了，我要投诉，第一句删了 | 我要投诉。 |
| 翻译成英文：大家好，我是新来的设计师李明。 | Hello everyone, I'm Ming Li, the new designer. |
| 不想去你的聚会，委婉一点 | 这次我可能去不了你的聚会了，不好意思。 |
| Please bring your 护照 to the airport | Please bring your 护照 to the airport.（中英混说原样保留） |

**任务 2：给出 0–3 条改写建议**，输出 JSON：`[{"label": "更正式", "text": "……"}]`。

两个任务的系统提示见 [voxflow/rewrite_prompts.py](https://github.com/ThermalEX/VoxFlow/blob/main/voxflow/rewrite_prompts.py)。训练时就用的这两段提示，推理时必须一字不差地使用。

## 文件

| 文件 | 大小 | 说明 |
| --- | --- | --- |
| `voxflow-rewrite-q8_0.gguf` | 1.9 GB | 推荐。显存约 2.5 GB，质量与原始权重一致 |
| `voxflow-rewrite-q4_k_m.gguf` | 1.2 GB | 显存更省，质量略低 |

根目录始终是当前推荐版本（现为 v4）。历代版本各放在自己的文件夹里，文件名带版本号，例如 `v1/voxflow-rewrite-v1-q8_0.gguf`：

| 版本 | 日期 | 种子数据 | 主要改动 |
| --- | --- | --- | --- |
| [v1](https://huggingface.co/ThermalEX/voxflow-rewrite/tree/main/v1) | 2026-10-13 | 1230 条 | 初版，覆盖 14 类口语现象 |
| [v2](https://huggingface.co/ThermalEX/voxflow-rewrite/tree/main/v2) | 2026-10-14 | 1269 条 | 中文姓名英译用“名 姓”顺序（张三 → San Zhang），称呼写作 Xiao Li、Lao Wang |
| [v3](https://huggingface.co/ThermalEX/voxflow-rewrite/tree/main/v3) | 2026-10-14 | 1321 条 | 姓名拼音：常见名字用字、多音字姓、复姓、隔音符号 |
| [v4](https://huggingface.co/ThermalEX/voxflow-rewrite/tree/main/v4) | 2026-10-15 | 1427 条 | 针对 v3 弱点补数据：有意义的“然后/就是”保留、中英夹杂保留、按位置删句、时间推算、只改语气的委婉改写。**当前推荐** |

各版本使用的测试集不同，指标不能直接横向比较；逐版本的评估见研究记录。

`runtime/` 目录里是 VoxFlow 软件内下载用的 llama.cpp b11596 Windows 版本（通用 Vulkan 版、NVIDIA CUDA 版及其 CUDA 运行库），从 [llama.cpp 官方发布页](https://github.com/ggml-org/llama.cpp/releases/tag/b11596) 原样转存（MIT 许可，见 `runtime/LICENSE-llama.cpp`），以便国内镜像也能下载；`catalog.json` 是软件读取的下载清单。

每个训练版本都打了标签（`v1`–`v4`）。下载时固定标签，以后更新模型也不会影响已发布的版本：

```
https://huggingface.co/ThermalEX/voxflow-rewrite/resolve/v4/voxflow-rewrite-q8_0.gguf
```

国内网络可以把域名换成 `hf-mirror.com`。

## 运行

```powershell
llama-server -m voxflow-rewrite-q8_0.gguf --port 8765 --alias voxflow-rewrite `
  --n-gpu-layers 99 --ctx-size 4096 --jinja --chat-template-kwargs '{"enable_thinking":false}'
```

然后通过 OpenAI 兼容接口调用 `http://127.0.0.1:8765/v1/chat/completions`，`temperature` 设为 0。**必须关闭思考模式**（`enable_thinking=false`），否则模型会先输出推理过程。

## 训练

- **基座**：Qwen/Qwen3.5-2B
- **方法**：bf16 LoRA，rank 16，学习率 2e-4，2 轮；Unsloth，在 RTX 3060 Laptop 6 GB 上训练约 34 分钟
- **数据**：1427 条手写种子，加上程序注入口气词、重复的扩增样本，共 3424 条（训练 3138 / 验证 134 / 测试 152）。覆盖 14 类口语现象：口气词、重复、即时纠正、回头删除 / 替换 / 补充、带理由的修正、口述格式、翻译与语气指令，以及要求原样保留的反例。数据全部是合成内容，不含真实用户数据。

## 评估（v4，测试集 152 条，Q8）

| 指标 | 未微调的 Qwen3.5-2B* | v4 |
| --- | --- | --- |
| 字符错误率 | 0.74 | **0.20** |
| 指令残留（“翻译成英文”等没删掉） | 31.9% | **0%** |
| 不该改的句子保持原样 | 81% | **95%** |
| 翻译 chrF | 39.5 | **64.8** |
| 建议 JSON 合法 / 符合规则 | 100% / 93% | **100% / 100%** |
| 单句延迟（中位数） | — | **0.14 s** |

\* 未微调模型是在早期较小的测试集（132 条）上测得的，仅供参考。

## 已知局限

- 时间推算可能出错，例如“九点开始，推迟一个半小时”会算成十一点。
- 句首有实际意义的“然后”有时会被当作口气词删掉。
- 委婉改写偶尔会改变原意。
- 中文人名英译时，个别生僻字的拼音可能出错。

完整的实验记录、各版本对比和问题分析见 [docs/research-log.md](https://github.com/ThermalEX/VoxFlow/blob/main/docs/research-log.md)。

## 许可

Apache License 2.0，与基座模型 Qwen3.5-2B 相同。
