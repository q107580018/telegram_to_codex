# README Restructure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 README 重构为统一快速开始文档，前半部分讲通用安装与启动，后半部分分平台说明 Telegram 和飞书。

**Architecture:** 只修改文档结构，不改运行时代码。保留现有内容要点，但重新组织标题、顺序和平台边界，让 README 与当前双平台能力一致，并同步把安装命令更新为 `uv` 工作流。

**Tech Stack:** Markdown, shell commands, uv

---

### Task 1: 重写 README 结构

**Files:**
- Modify: `README.md`

**Step 1: 重排标题与简介**

把标题改为 `CodexBridge`，在首段明确说明项目支持 Telegram 和飞书私聊，将消息桥接到本机 Codex CLI。

**Step 2: 重写快速开始与环境变量**

把安装依赖改成 `uv venv`、`uv pip install -r requirements.txt`，并将环境变量说明拆成通用项与平台项。

**Step 3: 重写启动与停止章节**

保留 `./start.sh tg`、`./start.sh feishu`、`./start.sh` 与 `./stop.sh` 的说明，把平台选择逻辑集中在这一节。

**Step 4: 拆分平台章节**

新增“平台配置差异”小节，分别给出 Telegram 和飞书所需配置、能力边界和启动方式。

**Step 5: 保留命令、App 与说明**

保留现有命令列表、macOS 控制器 App 与说明中的重要细节，只调整位置和平台归属。

### Task 2: 验证文档一致性

**Files:**
- Modify: `README.md`

**Step 1: 检查命令与脚本行为一致**

确认 README 中的启动命令与当前 `start.sh` / `stop.sh` 行为一致。

**Step 2: 检查环境变量与当前实现一致**

确认 Telegram 与飞书章节中的变量名与 `.env.example`、`config.py` 一致。

**Step 3: 进行快速文本检查**

运行 `sed -n '1,260p' README.md` 或等效命令，人工确认结构顺序、表述和信息完整性。
