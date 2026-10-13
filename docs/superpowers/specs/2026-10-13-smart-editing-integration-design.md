# 智能编辑接入 VoxFlow 设计

日期：2026-10-13
状态：设计已确认（对话中逐段确认），待实施计划

## 1. 目标

把已训练的口语改写模型（Qwen3.5-2B + LoRA，见 `2026-10-13-rewrite-dataset-design.md`）接入 VoxFlow 浮层，先试用效果；模型通过可替换的接口调用，设置里可以更换。

不做：GGUF 量化、浮层不抢焦点改造、更换 ASR、改写实时草稿。

## 2. 模型接口

- VoxFlow 只通过 **OpenAI 兼容的 Chat Completions 接口**调用改写模型：`POST {base}/chat/completions`，请求 `{"model", "messages", "max_tokens", "temperature": 0}`，读取 `choices[0].message.content`；健康检查 `GET {base}/models`。
- 两个任务共用一个接口，用 `voxflow/rewrite_prompts.py` 中的系统提示区分（训练、本地服务、软件三方共用此文件，`training/rewrite/prompts.py` 改为从这里导入）。
- 任务 1（清理）返回文本；任务 2（建议）返回 JSON 数组，解析失败或格式不符时视为无建议。
- 设置中的两种来源：
  - **VoxFlow 本地模型**：`http://127.0.0.1:8765/v1`，模型名 `voxflow-rewrite`，由 VoxFlow 自动启动。
  - **自定义接口**：用户填写地址、模型名、API Key（以 `Authorization: Bearer` 发送；保存在 QSettings，明文）。可指向 LM Studio、Ollama、llama.cpp server 或云端服务。
- 超时：清理 15 s、建议 20 s。失败或超时一律保留原文，状态栏提示，不影响上屏。

## 3. 本地模型服务

- `training/rewrite/serve.py`：在 WSL 训练环境中加载基座模型与 LoRA 适配器，使用标准库 `ThreadingHTTPServer` 提供上述两个接口；生成串行加锁；`enable_thinking=False`，贪心解码。
- 父进程退出时自动结束：服务监视 stdin，读到 EOF 即退出。
- VoxFlow 侧 `voxflow/local_server.py` 负责启动（`wsl.exe [-d 发行版] -- bash -lc "source <env>/bin/activate && cd <仓库 WSL 路径> && python -m training.rewrite.serve --adapter <路径> --port 8765"`，无窗口）、健康检查（就绪前按原文处理）和退出时关闭（关闭 stdin，再终止进程）。
- 高级设置（有默认值）：WSL 发行版（空 = 默认发行版）、训练环境路径（`~/voxflow-train`）、适配器路径（`training/rewrite/runs/qwen3.5-2b/adapter`）。

## 4. 设置界面

设置窗口新增分类 **Smart editing**：

- 开关：启用智能编辑（默认关闭，保证没有 WSL 环境时软件照常可用）。
- 模型来源下拉：VoxFlow local model / Custom endpoint。
- 自定义接口字段：Endpoint、Model、API key（密码框）；本地字段：WSL distro、Environment、Adapter。按来源显示对应字段。
- “Test connection” 按钮，显示可用或错误原因。
- 修改即时保存；更改来源或开关时启停本地服务。

## 5. 浮层交互

1. 停止录音并得到最终识别文字后，照常显示原文（可确认上屏）。
2. 启用且服务就绪时，后台请求任务 1。返回结果与原文不同时，**播放一次修改动画（约 0.8 s）**：
   - 小改动（字符相似度 ≥ 0.5）：删除部分加删除线并淡出，新增部分淡入。
   - 大改动（翻译、语气改写）：旧文字整体淡出，新文字淡入。
   - 动画结束后**只显示修改后的文字**。
3. 预览下方出现 **“撤回修改”** 按钮：鼠标悬停时预览区临时显示灰色原文，移开恢复；点击撤回为原文，按钮变为 **“恢复修改”**。
4. 随后请求任务 2，在预览下方与“撤回修改”同一行浮动显示 0–3 个建议按钮（显示标签，悬停显示完整内容）；点击采用该建议，此时“撤回修改”回到原文。
5. 用户开始编辑文字时，以当前文字为准；确认或 Enter 只粘贴当前文字。
6. 新录音开始、关闭浮层时丢弃未返回的改写结果（按会话编号判断）。
7. 网络调用在后台线程执行，由现有 `_poll` 定时器收取结果，界面不阻塞。

## 6. 测试

- 修改痕迹：分段 diff（中文按字、英文按词）、相似度、动画帧渲染。
- 接口客户端：用本地假 HTTP 服务测试成功、超时、错误码、建议 JSON 异常。
- 本地服务管理：用假命令测试启动、就绪、退出时关闭。
- 设置：字段保存与读取、按来源切换字段。
- 浮层：用假改写器测试改写替换、动画结束状态、撤回/恢复、悬停显示原文、建议采用、失败回退、过期结果丢弃。
- 端到端：启动本地服务，在浮层中实际说话验证。
