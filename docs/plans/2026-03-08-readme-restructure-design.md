# README Restructure Design

**Date:** 2026-03-08

## Goal

把 README 从“Telegram 机器人说明”重构为“CodexBridge 快速开始文档”，统一前半段安装与启动流程，再在后半段分别说明 Telegram 和飞书差异，避免飞书像追加附录。

## Current Problems

- 标题仍然是 Telegram 导向，与当前已支持飞书私聊不一致。
- 通用启动方式已经支持平台选择，但文档结构仍把飞书写成独立附录。
- 读者需要来回切换“通用说明”和“飞书说明”，难以快速定位配置差异。

## Approaches

### Approach 1: Keep README Telegram-first, append Feishu sections

延续当前结构，只在末尾补飞书章节。

**Pros**
- 改动最小

**Cons**
- 信息层级继续失衡
- 飞书仍然像附加功能
- 与项目现状不匹配

### Approach 2: Quickstart-first, unified setup then platform split

将 README 改成项目级入口：先写项目简介、统一依赖安装、环境变量、启动与停止；后面再拆平台差异、Telegram、飞书、命令与 App。

**Pros**
- 最符合当前项目状态
- 首屏信息更适合新用户
- 平台差异更清晰

**Cons**
- 需要重排现有内容

### Approach 3: Thin README plus separate platform docs

README 只保留统一入口，平台细节拆到独立文档。

**Pros**
- 首页更短

**Cons**
- 目前项目体量下会增加跳转成本
- 用户当前希望 README 本身更完整

## Recommendation

采用 Approach 2。

## Target Structure

1. 项目简介
2. 快速开始
3. 环境变量
4. 启动与停止
5. 平台配置差异
6. Telegram
7. 飞书
8. 命令
9. macOS 控制器 App
10. 说明

## Content Decisions

- 标题改为 `CodexBridge`
- 开头一句话同时覆盖 Telegram 和飞书私聊能力
- 统一安装步骤改成 `uv` 工作流，符合项目约定
- 平台启动方式集中放在“启动与停止”
- 把只属于 Telegram 的细节移到 Telegram 章节
- 把飞书说明从附录改成正式平台章节

## Risks

- README 重排时可能漏掉现有环境变量说明
- 平台章节若写得太细，会再次稀释快速开始部分

## Validation

- 通读 README，确认目录顺序符合目标结构
- 检查启动命令与当前脚本行为一致
- 确认 Telegram 与飞书各自的配置说明都可独立理解
