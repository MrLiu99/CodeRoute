# 流式解析压力案例

`14_streaming_csv` 包含三个公开函数：增量 UTF-8 解码、CSV 字段状态解析、字节流到记录的组合接口。输入块可以在字符、转义引号或 CRLF 中间断开；空字符串与空值必须区分，完整记录需要及时 yield。

公开测试 7 项，外部独立验收额外 6 项。要求和公开测试从运行开始就可见；不注入错误补丁、不在运行中变更测试，也不向 Agent 提供参考修复或外部验收代码。

```powershell
# 不调用模型，验证原始缺陷失败、参考修复通过
python evaluate.py --benchmarks benchmarks_streaming --config configs/default.json

# 四策略各两次，共八次真实运行
python evaluate.py --benchmarks benchmarks_streaming --live --repeats 2 --max-runs 8 --config configs/default.json
```

生成脚本为 `scripts/generate_streaming_benchmark.py`。这是自建诊断案例，不是标准 CSV 兼容性基准，也不保证模型第一次修复必然失败。只有轨迹中真实出现测试失败、Debugger 分析、再次修改及验收成功，才可作为成功纠错的证据。

本轮真实运行结果及预算诊断见 [评测报告](../docs/archive/RECHARGED_EVALUATION.md)。`configs/streaming-diagnostic.json` 使用 8192 输出 token、12 个角色回合，与默认配置结果单独统计。
