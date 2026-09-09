# SOP: State Workflow Operations (状态流转)

> **CRITICAL** — 开始前先读 [`../SKILL.md`](../SKILL.md)、[`workflow.md`](workflow.md)、[`error-handling.md`](error-handling.md)。

本 SOP 用于状态流工作项的状态变更操作。**仅适用于状态流**（pattern = State，如缺陷/issue），节点流请用 [`sop-transition-node.md`](sop-transition-node.md)。

> 此路径是 **conditional**（非 default-safe）。执行前先 `meegle inspect workflow.transition-state` 确认命令可用。

> 与上游 SaaS 版的关键差异（私有 cli）：
> - **按姓名查 userkey** 默认只用 `meegle user search --query "姓名" --project-key PROJ --format json`；若出现同名结果，展示候选 `email` / `user_key` 让用户确认。
> - **transition_id 必须从 query 获取**：不能猜测，每个空间/模板的 transition 配置不同。

---

## 写操作建模

流转前先明确：

- 目标对象：`project_key`、`work_item_type_key`、`work_item_id`、当前状态。
- 目标状态：目标状态名、`transition_id`、必填字段。
- 变更意图：推进、关闭、解决、重开或其他状态变更。
- 风险等级：状态流转是 conditional 写操作；通过 `inspect` 或 verified command surface 确认命令面，每次写前核对有效必填并服从用户与宿主授权。
- 结果核验：流转后回读状态，展示原状态、新状态、补充字段和执行结果。

## 执行流程

顺序：唯一确认目标/pattern/动作 → 读取可用流转 → 核对有效必填/权限 → 用户补缺值与确认 → dry-run → 执行 → 同目标回读。状态流转有写入副作用，即使 descriptor 标为 safe，也不豁免用户与宿主授权。

### STEP 1 — 定位工作项

从用户输入中提取 `work_item_id` 和 `project_key`：
- 用户给了 **URL** → `meegle url decode --url '<URL>' --format json`，直接使用返回的 `simple_name` 作为 `project_key`；空间发现条件见 [workitem.md](workitem.md#发现与复用)，不替代写权限、命令面或下方写前预校验
- 用户给了 **ID** → 需同时确定 `project_key`（优先用 profile 默认值）
- 信息不足时才追问

同时确认 `work_item_type_key`：
- `url decode` 返回的 `work_item_type` 只是 `api_name`，**不是** `work_item_type_key`
- 必须调用 `meegle workitem meta-types --project-key PROJ --format json`，按 `api_name` 映射出真实 UUID 形态的 `work_item_type_key`
- 映射失败时不要继续 `workflow` 命令，先停下来列出候选类型或让用户确认

拿到 `project_key + work_item_type_key + work_item_id` 后，先做一次轻量预校验：

```bash
meegle workitem get \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-ids '[12345]' \
  --format json
```

只有 `workitem get` 能成功命中目标工作项时，才继续后面的 `workflow list-state-transitions` / `workflow transition-state`。如果这里就报 `WorkItem Not Found`，优先回查 `project_key` 或 `work_item_type_key` 是否映射错，**不要**直接把同样的三元组继续喂给 workflow。

### STEP 2 — 查询当前状态和可用流转

```bash
meegle workflow list-state-transitions \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-id 12345 \
  --format json
```

从当前返回中识别当前状态与 connections 的 source/target、真实 `transition_id`（number）；`state_flow_nodes` / `connections` 的路径与条目以实际返回为准，见 [`workflow.md`](workflow.md) 的证据边界，不猜测缺失字段。

**确定目标状态：**
- 用户指定目标状态名 → 在当前可用 connections 中唯一匹配；重名、多个模板/状态或多条 transition 时列候选追问。
- 用户说“下一个状态” → 仅在当前状态只有一个符合意图的可用 transition 时继续；多个候选必须追问，不取返回首条。
- 没有匹配或目标/动作不明 → 展示候选确认，不自选其他 transition。
- 确认当前状态确无可用 transition 时告知终态/不可流转；返回结构未知不能当作终态。

### STEP 3 — 写前核对有效必填与用户输入

```bash
meegle workflow list-state-required \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-id 12345 \
  --node-id <target_state_key> \
  --mode unfinished \
  --format json
```

有效必填来源是同目标状态的必填接口，或当前配置明确要求；`--mode unfinished` 查询未完成必填。**空值不等于必填**，不能只因字段/角色为空就要求填写，不以真实流转失败探测必填。返回口径未知、条件要求不明或接口与配置矛盾时停止，披露未获取的证据，请用户在页面核对；不臆造 `required_fields[]` 非空条目结构。

任一有效必填缺真实值或不能通过当前公开且已核验的入口安全填写，就阻塞当前流转，不能等全部不可写才停止，也不能移除字段继续。硬拦截类型参考 [`error-handling.md`](error-handling.md) 的 Hard-Block Field Types；历史限制不等于本次逐字段业务验证。

缺值一次性汇总字段、类型、必填依据与可选项，等待用户提供真实值。人员、日期、枚举、文本、数字、布尔都不能编造默认值；仅可使用有来源的后端默认或用户已授权默认，并说明来源。无缺值、目标与授权明确时不重复追问，仍须预检/预览；API 可选不等于可以丢弃用户要求字段。

字段值唯一来源是 [`field-value-format.md`](field-value-format.md)：外层 `--fields` 是 JSON 数组编码，内层按字段类型保持原生值，文本仍为 string，数字/布尔保持原生值，结构化字段用对象/数组，不额外 stringify。generic array<object> 不代表全部字段可写；核对字段 key、类型、选项、作用域与当前状态入口支持，不把节点 owner/schedules 或 node_field 混入状态表单字段。

### STEP 4 — 预览并执行状态流转

以下文本字段和 transition_id 为占位；替换为用户真实值与 STEP 2 返回的数值 ID。无需补字段时省略 `--fields`，不能以此省略用户要求字段。

```bash
meegle workflow transition-state \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-id 12345 \
  --transition-id <transition_id> \
  --fields '[{"field_key":"xxx","field_value":"yyy"}]' \
  --dry-run \
  --format json
```

dry-run 只预览请求，不证明可写或已完成。核对同目标、全部输入及用户与宿主授权后，去掉 `--dry-run` 执行一次；当前状态/配置/用户输入变化时重新预检。若需单独补工作项字段，遵循更新 SOP，补写后回读并重新核对状态/必填；补充结果未知不能继续流转。

响应按文末恢复表分类：明确成功进入 STEP 5；超时等未知结果不直接重试；权限拒绝硬停。

### STEP 5 — 确认结果

```bash
meegle workflow list-state-transitions \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-id 12345 \
  --format json
```

核对同空间、同类型、同工作项 ID 的原状态、已确认 transition 的目标状态，以及本次补充字段。状态/表单值从同目标 workflow 回读，工作项级字段用 STEP 1 的 `workitem get` 回读；字段未返回不能当作已持久化。不能只凭 exit code / err_code 0 宣布完成。

回读失败、目标未到达或值不匹配时标记未验证或部分完成，展示实际状态、已确认字段与差异，不再次写入掩盖问题。完成汇报包含原状态 → 实际新状态、目标、补充字段摘要及未确认项。

---

## 字段补充规则

始终按 STEP 3 的有效必填、唯一格式来源与用户真实值构造，不维护第二套 STRING 协议。人员名称用公开 user search 查询并消歧，不自动指定人员；角色调整须核验状态专用参数、读旧值并保留非目标角色/成员。字段不可写时说明阻塞，不能自动换节点字段或其他入口绕过。

## 批量状态流转

只有用户明确授权多个状态步骤时才逐步执行，每步重新读取当前可用 transitions/有效必填、核对目标并回读。前一步结果未知或依赖阻塞时停止后续依赖流转，不自动改选 transition；保留并汇报已确认结果，后续步骤不假定独立。

## 错误恢复与熔断

通用规则见 [`error-handling.md`](error-handling.md)，以下顺序优先于所有补充与批量路径：

| 结果 | 处理 |
|---|---|
| 权限错误 | 权限拒绝立即停止当前业务目标的所有后续操作，包括读取、补字段、重试与后续流转；告知申请权限，不换身份/扩大查询 |
| 超时/断连/解析失败 | 结果未知，先只读核对同目标状态与本次字段；不能证明未落地则停止，请用户决定，不盲重试；到达目标也不等于所有字段已验证 |
| 明确拒绝且确认无副作用 | 重读当前状态、可用 transitions 与有效必填；同目标、同意图、契约有依据且授权仍有效时最多修正重试 1 次，再次失败停止 |
| transition_id 无效 / 必填缺失 / 类型错误 | 先按以上结果分类，再重核原目标与唯一格式索引；不自动改选其他 transition，不删字段，不尝试 STRING fallback |
| 无可用 transition、目标不唯一、任一必填不可写/缺真实值或口径未知 | 写前停止并说明；待用户处理后重新预检 |
| 返回成功但回读失败或不符 | 按 STEP 5 披露未验证或部分完成，不自动重写 |
