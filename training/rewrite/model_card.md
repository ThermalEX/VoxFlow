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

A 2B model that turns raw speech-recognition text into the text you meant to type: it removes fillers, applies spoken self-corrections ("Friday, no, Saturday"), follows inline voice commands ("translate to English", "make it more polite") and suggests up to three rewrites. Since v6 it also powers VoxFlow's memory: it picks out names, terms and plans worth remembering, fills in details a text leaves out, and summarizes a day of dictation. Fine-tuned from Qwen3.5-2B with LoRA and exported to GGUF for [llama.cpp](https://github.com/ggml-org/llama.cpp). It is the local smart-editing model of [VoxFlow](https://github.com/ThermalEX/VoxFlow), a Windows voice-input app.

---

VoxFlow 的本地智能编辑模型：把语音识别得到的口语原文，整理成真正想输入的文字；从 v6 起也负责记忆功能（提取值得记住的信息、按记忆补全、每日总结）。基于 Qwen3.5-2B 做 LoRA 微调，导出为 GGUF，在 6 GB 显存的笔记本上单句约 0.14 秒。

## 能做什么

模型有五个任务，用不同的系统提示区分：

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

**任务 3（v6 起）：提取值得记住的信息**，输出 JSON。时间照抄原话，具体日期由软件按规则换算：

| 输入 | 输出 |
| --- | --- |
| 今天是10月20日。文字：周三下午三点开评审会，张三主持 | `[{"kind": "event", "content": "评审会", "time": "周三下午三点"}, {"kind": "person", "content": "张三"}]` |
| 今天是10月20日。文字：好的，收到，谢谢！ | `[]` |

**任务 4（v6 起）：按记忆补全**。记忆“评审会（周三下午三点）”，文字“提醒大家参加评审会。” → “提醒大家参加周三下午三点的评审会。”；记忆与文字无关或已写明时原样输出。

**任务 5（v6 起）：每日总结**，按“日程与会议 / 待办事项 / 提到的人和事”分点，不超过 300 字。

各任务的系统提示和用户消息格式见 [voxflow/rewrite_prompts.py](https://github.com/ThermalEX/VoxFlow/blob/main/voxflow/rewrite_prompts.py)。训练时就用的这些提示，推理时必须一字不差地使用。

## 文件

| 文件 | 大小 | 说明 |
| --- | --- | --- |
| `voxflow-rewrite-q8_0.gguf` | 1.9 GB | 推荐。显存约 2.5 GB，质量与原始权重一致 |
| `voxflow-rewrite-q4_k_m.gguf` | 1.2 GB | 显存更省，质量略低 |

根目录始终是当前推荐版本（现为 v6）。历代版本各放在自己的文件夹里，文件名带版本号，例如 `v1/voxflow-rewrite-v1-q8_0.gguf`：

| 版本 | 日期 | 种子数据 | 主要改动 |
| --- | --- | --- | --- |
| [v1](https://huggingface.co/ThermalEX/voxflow-rewrite/tree/main/v1) | 2026-10-13 | 1230 条 | 初版，覆盖 14 类口语现象 |
| [v2](https://huggingface.co/ThermalEX/voxflow-rewrite/tree/main/v2) | 2026-10-14 | 1269 条 | 中文姓名英译用“名 姓”顺序（张三 → San Zhang），称呼写作 Xiao Li、Lao Wang |
| [v3](https://huggingface.co/ThermalEX/voxflow-rewrite/tree/main/v3) | 2026-10-14 | 1321 条 | 姓名拼音：常见名字用字、多音字姓、复姓、隔音符号 |
| [v4](https://huggingface.co/ThermalEX/voxflow-rewrite/tree/main/v4) | 2026-10-15 | 1427 条 | 针对 v3 弱点补数据：有意义的“然后/就是”保留、中英夹杂保留、按位置删句、时间推算、只改语气的委婉改写 |
| [v5](https://huggingface.co/ThermalEX/voxflow-rewrite/tree/main/v5) | 2026-10-18 | 1589 条 | **已弃用，无模型文件**：名句纠错有所改善，但建议偏向语气调整、风格改写退步；仅保留实验说明 |
| [v6](https://huggingface.co/ThermalEX/voxflow-rewrite/tree/main/v6) | 2026-10-20 | 1833 条 | 新增记忆的三个任务（提取 186、补全 89、总结 35 条）；补充按位置删句、即时纠正、一句话的正式改写等 96 条整理样本。**当前推荐** |

v5 曾训练和评测，但效果不如 v4，模型文件在公开发布前已删除；上方链接仅指向弃用说明，不能下载模型。v1–v3 与 v4 使用的测试集不同，指标不能直接横向比较；v6 与 v4 使用同一测试集。逐版本的评估见研究记录。

`runtime/` 目录里是 VoxFlow 软件内下载用的 llama.cpp b11596 Windows 版本（通用 Vulkan 版、NVIDIA CUDA 版及其 CUDA 运行库），从 [llama.cpp 官方发布页](https://github.com/ggml-org/llama.cpp/releases/tag/b11596) 原样转存（MIT 许可，见 `runtime/LICENSE-llama.cpp`），以便国内镜像也能下载；`catalog.json` 是软件读取的下载清单。

每个发布的版本都打了标签（`v1`–`v4`、`v6`）。下载时固定标签，以后更新模型也不会影响已发布的版本：

```
https://huggingface.co/ThermalEX/voxflow-rewrite/resolve/v6/voxflow-rewrite-q8_0.gguf
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
- **方法**：bf16 LoRA，rank 16，学习率 2e-4，2 轮，914 步；Unsloth，在 RTX 3060 Laptop 6 GB 上训练约 42 分钟，峰值显存 4.4 GB
- **数据**：1833 条手写种子（整理 1097、建议 426、记忆任务 310），加上程序注入口气词、重复的扩增样本，训练 3650 / 验证 163 条。整理任务覆盖 14 类口语现象：口气词、重复、即时纠正、回头删除 / 替换 / 补充、带理由的修正、口述格式、翻译与语气指令，以及要求原样保留的反例。数据全部是合成内容，不含真实用户数据。

## 评估（v6 与 v4，Q8）

整理与建议任务（测试集 152 条，与 v4 相同）：

| 指标 | 未微调的 Qwen3.5-2B* | v4 | v6 |
| --- | --- | --- | --- |
| 字符错误率 | 0.74 | 0.198 | 0.202 |
| 指令残留（“翻译成英文”等没删掉） | 31.9% | 0% | 0% |
| 不该改的句子保持原样 | 81% | 95% | 95% |
| 翻译 chrF | 39.5 | 64.8 | 60.0 |
| 建议 JSON 合法 / 符合规则 | 100% / 93% | 100% / 100% | 100% / 100% |
| 单句延迟（中位数） | — | 0.14 s | 0.14 s |

\* 未微调模型是在早期较小的测试集（132 条）上测得的，仅供参考。v6 Q8 的翻译 chrF 比 v4 低 4.8，但 Q4 上两者持平（62.4 / 62.6），翻译样本只有 19 条，差异需更大的测试集确认。

记忆任务（手写评测集：提取 36 条、补全 20 条、总结 5 天，不参与训练）：

| 指标 | v4（只靠提示） | v6 |
| --- | --- | --- |
| 提取召回率 / 精确率 | 54% / 61% | **94% / 81%** |
| 寒暄、琐事不乱记 | 38% | **88%** |
| 安排的时间写对 | 54% | **85%** |
| 补全：漏掉的信息补上 | 58% | **100%** |
| 补全：不该补的原样保留 | 63% | **88%** |
| 总结要点覆盖率 | 81% | **96%** |
| 编造的数字 | 0 | 0 |

## 已知局限

- 时间推算可能出错，例如“九点开始，推迟一个半小时”会算成十一点。
- 句首有实际意义的“然后”有时会被当作口气词删掉。
- 委婉改写偶尔会改变原意。
- 中文人名英译时，个别生僻字的拼音可能出错。
- 提取偶尔漏掉称呼（如“张总”），或多记一条相关的事实。

完整的实验记录、各版本对比和问题分析见 [docs/research-log.md](https://github.com/ThermalEX/VoxFlow/blob/main/docs/research-log.md)。

## 许可

Apache License 2.0，与基座模型 Qwen3.5-2B 相同。
