# 更新记录

本文件用于记录每次提交的主要更新内容。后续每次提交前都需要更新本文件，并在 git commit 信息中简明说明具体改动点。

## 2026-05-22

### 重构为科学计算版 CDR 工程

- 将原单文件实现拆分为 `cdr/` 包，新增配置、信号生成、CDR 恢复、绘图和 CLI 编排模块。
- 使用 `numpy` 生成 bit、边界、抖动、噪声并进行向量化固定采样分析。
- 使用 `scipy.signal.lfilter()` 实现一阶低通信道模型，替代手写逐样点信道循环。
- 使用 `pandas` 汇总固定采样器和 CDR 结果，并导出结构化 CSV。
- 使用 `matplotlib` 生成相位误差图和诊断面板，包含接收波形、周期收敛和眼图视图。
- 在终端摘要和 JSON 中输出周期恢复 ppm 误差，便于直接判断 CDR 是否锁到真实 UI。
- 新增 `pyproject.toml`，支持以包形式安装，并提供 `cdr-demo` 命令行入口。
- 为 `cdr/cli.py` 增加模块入口保护，支持 `python3 -m cdr.cli`。
- 将默认运行输出改到 `outputs/`，并在 `.gitignore` 中忽略该目录。
- 重写 `docs/CDR_DEMO_EXPLAINED.md`，按新架构讲解 CDR 原理、文件构成规则、输出字段和 git 维护规则。
- 新增 `docs/images/refactored_architecture.svg`，展示重构后的模块数据流。
- 在新版说明中重新引用 CDR 环路图和 Alexander 相位检测图，并移除旧版单文件流程图。
- 移除根目录旧版示例相位图，避免与新的 `outputs/` 生成规则冲突。

### 新增科学计算依赖环境

- 检查当前 Python 环境，确认 `numpy`、`matplotlib`、`scipy`、`pandas` 尚未安装。
- 因 Homebrew Python 启用了 PEP 668 系统环境保护，改为在项目 `.venv` 虚拟环境中安装依赖。
- 新增 `requirements.txt`，记录可复现安装的直接依赖版本。
- 更新 `README.md`，补充虚拟环境创建和依赖安装命令。
- 更新 `.gitignore`，明确忽略本地虚拟环境 `.venv/`。

### 建立 CDR demo 项目

- 将 CDR 仿真程序整理到本地目录 `/Users/ganxuanzhi/vscode-demo/CDR`。
- 保留核心脚本 `cdr_demo.py`，用于生成 NRZ/PAM2 信号并演示数字 CDR 锁定过程。
- 保留详细说明文档 `docs/CDR_DEMO_EXPLAINED.md`，包含程序流程、函数拆解、公式、表格和图示说明。
- 保留三张解释用 SVG 图片：脚本流程图、CDR 环路图、Alexander 相位检测器图。
- 保留示例相位误差图 `cdr_demo_phase.svg`，便于在 GitHub 上直接查看 CDR 与固定采样的对比。
- 新增 `README.md`，说明项目用途、运行方式、输出文件和维护约定。
- 新增 `.gitignore`，忽略可重新生成的 CSV 输出、Python 缓存和系统临时文件。
