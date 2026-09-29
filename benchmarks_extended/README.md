# 扩展跨文件案例

三个独立案例覆盖递归配置合并、批量转账回滚、多租户缓存。原始十个案例仍在 `benchmarks/`。

Agent 仅访问各案例的 `repo/` 与 `issue.txt`；`holdout/` 与 `case.json` 的参考修改不提供给 Agent。没有强制模型生成错误补丁。

```powershell
python evaluate.py --benchmarks benchmarks_extended --config configs/default.json
```

默认验证不调用模型。生成脚本为 `scripts/generate_extended_benchmarks.py`；真实运行及接口故障记录见 [验证报告](../docs/archive/REVIEWER_FOLLOWUP.md)。
