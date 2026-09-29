# 模型响应与思考模式诊断（2026-09-29）

上一轮流式案例的多次响应正文为空，输出额度被思考消耗；旧客户端没有保留 `finish_reason`，Harness 将空正文当成普通 JSON 错误继续请求，直到回合耗尽。本次针对该阻碍修改接入层。

## 行为

- `ModelReply` 保存服务端 `finish_reason`；`content=null` 规范化为空字符串，保留已返回的 token 用量。
- `length` 标为 `output_truncated`；空白正文标为 `empty_response`；其他非正常结束原因标为 `unexpected_finish_reason`。即使正文恰好构成合法 JSON，`length` 响应也不执行工具。
- 主模型遇到上述响应时记录用量、结束原因、错误类别，然后结束运行，不自动重复付费请求。指标中的 `response_errors` 按错误类型计数，结束状态为 `execution_error`。
- Hybrid 轻量响应无效时仍可升级主模型；所有调用计入共享预算，预算耗尽不会升级。
- 正常结束但 JSON 格式错误仍采用原来的有界纠正流程，不提取或执行多对象响应中的部分动作。
- 角色提示要求一次只发一个动作，使用较小的源码替换，并为提交结果预留最后一回合。

## 配置

`thinking_mode` 配置主模型，`lightweight_thinking_mode` 独立配置轻量模型。取值：

| 值 | 请求行为 |
|---|---|
| `""`（默认） | 不发送该参数，遵循提供商默认行为 |
| `"enabled"` | 发送 `thinking: {type: "enabled"}` |
| `"disabled"` | 发送 `thinking: {type: "disabled"}` |

该请求字段按 [DeepSeek 官方 Chat Completions 文档](https://api-docs.deepseek.com/api/create-chat-completion/) 实现，只有支持此字段的提供商才能显式配置。主模型参数不会继承到 OpenRouter 轻量客户端。默认配置未改变；显式非思考示例为 `configs/nonthinking.example.json`，其他模型、预算与 `configs/default.json` 一致。

```powershell
python evaluate.py --benchmarks benchmarks_streaming --live --workflows dynamic hybrid --repeats 2 --config configs/nonthinking.example.json
```

命令最多执行四次真实修复，会调用付费接口。输出上限 4096、角色回合 8；没有沿用上轮扩大预算的设置。

## 验证计划与记录

自动化测试覆盖请求字段、空正文与结束原因保留、无效响应禁止执行工具、用量不丢失、轻量回退与总预算限制。既有 81 项加本轮 15 项均通过（先执行 94 项完整套件，再执行包含新增两项的 15 项响应测试）。

本轮单独保存四次流式运行和一次发票回归，不覆盖以前的失败记录：

- 流式：`runs/eval-20260929-122746-028ae146`
- 发票：`runs/eval-20260929-122756-991a40f9`

思考设置、角色提示和异常处理均有变化，因此这是一组修复后的功能验证，不是只改变思考模式的严格消融对照。并行运行也不适合直接比较延迟。

## 真实结果

| 运行 | Harness 状态 | 独立验收 | 最终成功 |
|---|---|---|---|
| 发票 dynamic | succeeded | passed | 是 |
| 流式 dynamic r1 | execution_error：空白正文 | passed | 否 |
| 流式 hybrid r1 | succeeded | failed（11/13） | 否 |
| 流式 hybrid r2 | succeeded | failed（11/13） | 否 |
| 流式 dynamic r2 | budget_exhausted：Developer 八回合耗尽 | failed | 否 |

全部 105 次模型响应的 `finish_reason` 均为 `stop`，因此本批次没有实际观测到 `length`；截断拒绝执行的行为由自动化测试验证。流式批次出现 2 次普通 JSON 协议错误，以及 1 次空白正文响应；空白响应包含空白字符而非有效 JSON，新检查记录其 221 个输出 token 后立即停止，没有继续浪费剩余回合。`stop` 并不保证响应正文可用。

### Debugger 证据与边界

`14_streaming_csv-hybrid-r1` 首次公开测试失败，按实际步骤 **3 Tester → 4 Debugger → 5 Developer → 6 Tester** 完成了修复后的公开测试恢复，随后 Reviewer 接受。两个测试对应不同源码 revision。但独立验收发现 BOM 未正确去除，导致两个测试失败，所以最终仍为失败。

`14_streaming_csv-dynamic-r1` 前两次 Tester 均失败，Debugger 介入一次；第三次 Developer 修改后的补丁通过了事后独立验收，但 Developer 随后返回空白正文，未提交，也没有后续 Harness Tester/Reviewer，因此同样不算成功恢复。不能用独立验收反向补齐未完成的工作流。

四次流式运行合计 3 次实际公开测试失败、2 次 Debugger 调用、1 次公开测试恢复、**0 次最终验收成功的 Debugger 恢复**。现在已有真实调度与修复动作的证据，但通用正确性和完整成功仍未验证。

### 核对与用量

两个批次的运行组合完整、源码与案例指纹未变、公开测试未改；Harness 成功记录的测试与审查 revision 一致；产物未发现本地 API 密钥。每批次保存 `audit.json` 和 `recovery_summary.json`。

五次真实运行共 105 次模型调用，输入 218,354 token、输出 14,366 token。数据用于核对实际调用，不是账单金额；不同批次包含不同提示与流程长度，不能直接推断思考模式的因果效果。

本次非思考配置流式结果为 0/4，不能称为性能或成功率提升；保留为可选示例，不替换默认配置。后续应重点提高 issue 要求覆盖与审查质量，并为 BOM 等明确需求加入新的公开回归案例版本；原测试集与失败结果应保留，不能在原评测中补测试后冒充同一批次成功。
