# SOP: Node Workflow Operations (节点流转)

> **CRITICAL** — 开始前先读 [`../SKILL.md`](../SKILL.md)、[`workflow.md`](workflow.md)、[`error-handling.md`](error-handling.md)。

本 SOP 用于节点流工作项的节点完成（confirm）/ 回滚（rollback）操作。**仅适用于节点流**（pattern = Node），状态流请用 [`sop-transition-state.md`](sop-transition-state.md)。

> 此路径是 **conditional**（非 default-safe）。执行前先 `meegle inspect workflow.transition` 确认命令可用。

> 与上游 SaaS 版的关键差异（私有 cli）：
> - **按姓名查 userkey** 默认只用 `meegle user search --query "姓名" --project-key PROJ --format json`；若出现同名结果，展示候选 `email` / `user_key` 让用户确认。
> - **`workitem update` 的 `role_operate` 不可用**：但 `workflow transition` 的 `--role-assignee` 参数可以在流转时填充角色。

---

## 写操作建模

流转前先明确：

- 目标对象：`project_key`、`work_item_type_key`、`work_item_id`、当前节点。
- 目标状态 / 节点：目标节点、`node_id`、动作 `confirm` / `rollback`。
- 变更意图：推进、回滚、补充节点字段或角色。
- 风险等级：流转是 conditional 写操作；通过 `inspect` 或 verified command surface 确认命令面，每次写前核对有效必填并服从用户与宿主授权。
- 结果核验：流转后回读 workflow 状态，展示原节点、目标节点、补充字段和执行结果。

## 核心设计原则：写前核对，不以写入探测

定位且唯一确认目标/pattern/动作 → 读取可用流转 → 核对有效必填/权限 → 用户补缺值与确认 → dry-run → 执行 → 同目标回读。

`workflow transition` 只接受 `node_id`（节点 key），不支持节点名称。先从 `workflow list-state-transitions` 获取目标映射和当前状态，再查询必填；不以真实流转失败探测缺失项。

---

## 执行流程

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

只有 `workitem get` 能成功命中目标工作项时，才继续后面的 `workflow list-state-transitions` / `workflow transition`。如果这里就报 `WorkItem Not Found`，优先回查 `project_key` 或 `work_item_type_key` 是否映射错，**不要**直接把同样的三元组继续喂给 workflow。

### STEP 2 — 查询节点状态

```bash
meegle workflow list-state-transitions \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-id 12345 \
  --format json
```

从返回中定位目标节点的 ID、名称和当前状态；字段路径以当前返回为准，参考 [`workflow.md`](workflow.md) 的证据边界，不能猜测缺失的节点配置。

**确定目标节点与操作：**
- 用户指定节点名 → 唯一匹配后取得真实 node_id；重名或多个进行中节点时列出候选追问。
- 用户说“当前节点”或未指定节点 → 仅在意图与当前状态能唯一定位时继续，不按返回顺序选择。
- 用户说“所有节点” → 先确认范围与顺序，再按文末批量规则逐步核验。
- “完成/推进/确认”对应 `confirm`；“回滚/退回”对应 `rollback`，并确认回滚原因；动作不明时追问，不默认推进。

### STEP 3 — 写前核对有效必填与用户输入

```bash
meegle workflow list-state-required \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-id 12345 \
  --node-id <node_key> \
  --mode unfinished \
  --format json
```

有效必填来源是同目标的必填接口，或当前节点配置中明确的要求；`--mode unfinished` 用于未完成必填，不据此臆造返回条目结构。见 [`workflow.md`](workflow.md)：本地 fixture 仅证明空 `required_fields` 包装，未覆盖非空条目/条件必填语义。返回无法解释或配置与接口矛盾时停止，披露未获取的口径，请用户在页面核对，不用写入试探。

**空值不等于必填**：fields、角色 owners、排期为空或时间为 0，只是待核对候选，不能据此强制补值；未被要求的可选字段仅按用户意图填写。

- 缺值一次性列出字段、类型、必填依据和可选项，等待用户提供真实值。人员、日期、枚举、文本、数字、布尔均不猜测，不编造 false/估分等默认值。
- 仅可使用有明确来源的后端默认或用户已授权默认，并说明来源；API 可选不等于可丢弃用户要求字段。
- 任一有效必填无法通过已公开且已核验的入口安全填写，即阻塞整个当前流转；不能移除该字段继续。硬拦截类型见下表。
- 无缺值且用户意图/授权明确时无需重复追问，但仍完成写前核对和预览。目标、补充范围或授权不明时先确认。

**硬拦截字段（不能作为通用字段自动补写）：**

| 字段类型 | 处理 |
|---|---|
| `actual_work_time` | 页面登记 |
| `node_finished_conclusion` / `node_finished_opinion` | 历史记录存在静默忽略，不能靠 success 判断写入 |
| `owners_finished_info` | 各负责人在页面操作 |
| `vote-boolean` / `vote-option` / `vote-option-multi` | 页面交互 |
| `compound_field` / `multi_user_compound_field` | 当前路径未证明安全支持 |
| `file` / `multi-file` / `multi_file` | 不通过通用 fields 上传；页面或另行授权的公开附件路径 |
| 计算字段 | 只读 |

输出受阻节点、字段名/类型、原因与待用户操作，不自动换命令绕过。以上沿用历史限制，不代表本次逐类型业务验证。

### STEP 4 — 构造字段并预览必要补充

字段值唯一来源是 [`field-value-format.md`](field-value-format.md)。外层 `--fields` 是 JSON 数组编码，内层 `field_value` 保留字段规定的原生类型：文本仍为 string，数字/布尔保持原生值，结构化字段为对象/数组，不额外 stringify。generic array/object descriptor 不代表全部字段可写；先核对真实字段类型、合法 key、选项、作用域与当前入口支持。

**节点专属属性与表单字段不得混用：**

| 类型 | 入口与边界 |
|---|---|
| 节点负责人 | `workflow update-node --node-owners`；不放进 fields |
| 节点统一排期 | `different_schedule=false` 时 `--node-schedule` object |
| 节点差异排期 | `different_schedule=true` 时 `--schedules` array<object>，owners 对应真实负责人 |
| 节点估分 | 对应排期对象的 `points`；不造默认值 |
| 节点角色 | 仅核验配置和授权后使用 `--role-assignee`；保留非目标角色/成员 |
| `form_item_type = "node_field"` | `workflow update-node --fields` 或 `workflow transition --fields` |
| `form_item_type = "field"` | 工作项字段走 `workitem update --update-fields`，遵循更新 SOP，不把节点字段送入该入口 |

`form_item_type` / `field_type_key` 仅在当前返回或配置明确提供时用于分类，未知作用域不猜测。节点表单 schedule 字段与节点排期不是同一种 shape；表单字段示例（字段 key、时间均为占位，使用前替换为已核验且用户提供的值）：

```json
[{"field_key":"field_225087","field_value":{"start_time":1722182400000,"end_time":1722355199999}}]
```

下面是三个**独立预览示例**，不是让每次流转都执行三次补充；只选择用户要求/有效必填所需的路径。统一排期与差异排期二选一；`different_schedule` 未获取时停止排期补写。当前 descriptor/源码未声明 owner 与 schedule 同写互斥，但未证明后端组合行为；本 SOP 保守分开更新，删除历史“同时传却说不可同时”的矛盾。

```bash
# 节点负责人预览
meegle workflow update-node \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-id 12345 \
  --node-id <node_key> \
  --node-owners '["userkey1"]' \
  --dry-run \
  --format json

# 统一排期预览（different_schedule=false）
meegle workflow update-node \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-id 12345 \
  --node-id <node_key> \
  --node-schedule '{"estimate_start_date":1722182400000,"estimate_end_date":1722355199999,"points":5,"is_auto":false}' \
  --dry-run \
  --format json

# 差异排期预览（different_schedule=true，不与上一示例同时使用）
meegle workflow update-node \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-id 12345 \
  --node-id <node_key> \
  --schedules '[{"owners":["userkey1"],"estimate_start_date":1722182400000,"estimate_end_date":1722355199999,"points":5,"is_auto":false}]' \
  --dry-run \
  --format json
```

dry-run 仅检查请求，不证明字段可写或已落地。核对预览目标、字段与授权后，才可去掉 `--dry-run` 执行必要的补充；每次补充后立即按 STEP 6 回读对应字段，再重新查询当前状态/有效必填。任一补充结果未知或不匹配时停止，不能继续流转。追加操作写前读取并保留旧值，不能覆盖非目标成员。

### STEP 5 — 预览并执行流转

完成 STEP 3/4 后预览：

```bash
meegle workflow transition \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-id 12345 \
  --node-id <node_key> \
  --action confirm \
  --dry-run \
  --format json
```

如果当前入口支持同次补充已核验的节点表单字段，可在流转预览中带入；以下仅为文本字段示例，不是默认补值：

```bash
meegle workflow transition \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-id 12345 \
  --node-id <node_key> \
  --action confirm \
  --fields '[{"field_key":"xxx","field_value":"yyy"}]' \
  --dry-run \
  --format json
```

回滚改为 `--action rollback` 并加 `--rollback-reason "用户确认的原因"`，同样先核对当前可用动作/必填与授权。预览通过且符合用户与宿主授权后，去掉 `--dry-run` 执行一次；目标或输入发生变化则重新预检，不直接使用过期预览。

### STEP 6 — 同目标回读与返回结果

实际补充/流转后，用 `workflow list-state-transitions` 回读同空间、同类型、同工作项 ID 的目标 node_id，核对动作预期的节点状态及本次补充字段、owner/排期/角色。工作项级字段用 `workitem get` 回读同一三元组。回读方式与 STEP 1/2 相同，不以同名其他工作项替代。

不能只凭 exit code / err_code 0 宣布成功；字段未返回不能当作已持久化。回读失败、状态未到达或字段不匹配时标记未验证或部分完成，列出已确认结果和差异，不再次写入掩盖问题。汇报原节点、目标节点、动作、补字段、实际状态与未完成项。

---

## 批量流转

先确认用户授权的节点范围、动作和依赖顺序；每一步都重新执行写前状态/有效必填核对与写后回读。前一步结果未知或依赖阻塞时停止后续依赖流转，不自动跳到下一个节点；已确认完成的节点保留并单独汇报，继续其他独立目标须符合既有授权，不能推定独立性。

## 错误恢复与熔断

通用规则见 [`error-handling.md`](error-handling.md)，以下顺序优先于任何补充/批量路径：

| 结果 | 处理 |
|---|---|
| 权限错误 | 权限拒绝立即停止当前业务目标的所有后续操作（包括读取、补字段、重试与依赖流转），告知申请权限，不换身份/扩大查询 |
| 超时/断连/解析失败 | 结果未知，先只读核对同目标状态与本次字段；不能证明未落地则停止，请用户决定，不盲重试；即使已到目标，也不宣称未核验字段完成 |
| 明确拒绝且确认无副作用 | 仅重读当前状态/可用动作/有效必填后，保持同目标和用户意图、有契约依据且授权仍有效时最多修正重试 1 次；再次失败停止 |
| node not found / 必填缺失 / field illegal / 类型错误 | 先按以上结果分类；核对真实 node_id、作用域和唯一格式索引，不自动改选节点、删字段或尝试 STRING fallback |
| 目标消失、配置不明、任一必填不可写或缺真实值 | 写前停止，一次性说明阻塞项；待用户补值/页面处理后重新预检 |
| 返回成功但回读失败或不符 | 按 STEP 6 披露未验证或部分完成，不自动重写 |
