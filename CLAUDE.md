# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

量化交易学习项目。目标是系统学习量化交易的核心概念、实践策略开发与回测，从基础的双均线策略开始逐步深入。用户（Chao Zhou）是量化交易初学者，目前处于第二周学习阶段。

## 当前状态

已有第一周双均线策略回测基础，正在进行第二周学习。现有文件：
- `第一周任务.txt` — 第一周学习目标与打卡内容
- `第二周任务.txt` — 第二周学习目标与打卡内容
- `第二周报告_草稿.md` — 第二周报告（高股息/低估值策略）
- `高股息低估值策略.py` — 高股息/低估值聚宽策略代码
- `资源.csv` — 推荐的学习资源列表（聚宽、米筐、QuantConnect、开源教程等）

## 项目规划

每周一个学习阶段，逐步深入：
1. **第一周** ✅ — 理解量化交易核心概念、双均线策略回测实践（已完成）
2. **第二周** 🏃 — 完整跑通策略调研→实现→回测流程，当前已选高股息/低估值策略
3. **后续周** — 逐步增加策略复杂度、实盘模拟（待定）

## 推荐平台与工具

- **回测平台**：聚宽(joinquant.com)、米筐、QuantConnect — 初学者推荐使用平台，省去数据/系统搭建
- **学习资源**：Whale-Quant(Datawhale)、Awesome-Quant、聚宽社区文档
- **AI 辅助**：可用于理解概念和辅助调试，但需自行思考筛选

## 使用方法

- 当前暂无构建/测试命令，代码编写后补充
- 策略文件可基于平台（如聚宽）的 Python API 编写
- 数据分析和回测结果可用 Jupyter notebook 记录

## 核心代码API文档
https://www.joinquant.com/help/api/help#name:api