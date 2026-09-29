# CodeRoute

一个面向小型 Python 项目的多智能体代码修复工具。输入代码仓库和问题描述，CodeRoute 会分析代码、生成修改、运行测试，并根据反馈继续修复和审查，最后输出补丁与执行记录。

主模型使用 **DeepSeek**，轻量路由通过 **OpenRouter / Qwen** 提供。无需部署本地模型。

## 能做什么

- **五角色协作**：Analyzer 定位问题、Developer 改代码、Tester 跑测试、Debugger 分析失败、Reviewer 审查补丁。
- **动态选择下一步**：明确的步骤交给规则，其余由轻量模型判断，必要时回退到主模型。
- **过程可查看**：保留角色轨迹、测试日志、模型调用量、token 和耗时。

典型路径：

```text
分析 → 修改 → 测试 → 审查 → 输出补丁
               ↓ 失败
             诊断 → 再次修改 → 再次测试
```

支持 `fixed`、`llm`、`dynamic`、`hybrid` 四种多角色工作流，推荐从 `hybrid` 开始。

## 快速开始

需要 **Python 3.9+、Git**。在项目根目录执行，建议使用虚拟环境：

```bash
python -m pip install -e .

# 先跑无费用演示，模型动作由脚本模拟，文件修改和测试真实执行
python main.py --repo examples/demo_repo --issue-file examples/issue.txt --mode mock --workflow hybrid --config configs/release.json
```

使用真实模型时，复制 `.env.example` 为 `.env`，填入两个密钥：

```dotenv
DEEPSEEK_API_KEY=你的DeepSeek密钥
OPENROUTER_API_KEY=你的OpenRouter密钥
```

然后运行：

```bash
python main.py --repo examples/demo_repo --issue-file examples/issue.txt --mode live --workflow hybrid --config configs/release.json
```

修复自己的项目时，替换 `--repo` 和 `--issue-file`。项目依赖需要提前安装好，测试使用 pytest。真实运行会产生 API 用量，密钥不要上传到 GitHub。

结果保存在 `runs/` 的独立目录中，重点查看 `final.diff`、`final_state.json`、`trajectory.json` 和 `metrics.json`。

## 测试与效果

当前版本 **124 项工程测试通过**；固定的 14 个自建修复任务中，Hybrid **成功 13 个（92.9%）**。基础和跨文件案例全部通过，复杂流式解析案例仍有边界问题。每个案例只运行一次，这个结果主要用于展示当前项目效果。

```bash
# 工程测试，不调用模型
python -m pytest -q

# 校验案例与参考修复，不调用模型
python evaluate.py --suite configs/release-suite.json --config configs/release.json
```

完整真实评测命令见使用文档。项目目前适合小型、可信的 Python 仓库，不自动安装依赖，不修改测试或配置文件，不保证所有复杂问题都能修好。

## 更多说明

源码在 `src/coderoute/`，测试在 `tests/`，运行配置在 `configs/`。`release.json` 是当前主线配置；历史实验记录保留在 `docs/archive/`。
