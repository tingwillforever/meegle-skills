# 工作流辅助命令

工作流流转之前用来查询可流转方向、必填项、节点字段配置的辅助命令。核心流转命令（`workflow transition` 节点流 / `workflow transition-state` 状态流 / `workflow update-node`）见 SKILL.md 主文件 + `sop-transition-node.md` / `sop-transition-state.md`。

## 与 upstream 差异

| upstream 命令 | 本地 CLI | 说明 |
|---|---|---|
| `workflow meta-node-fields` | 不支持 | MCP 无对应工具，用 `workflow list-state-transitions` 返回的 `workflow_nodes[].fields` 替代 |

命令参数以当前 public inspect 为准，不由 upstream 名称相似推断兼容。字段值统一查 [`field-value-format.md`](field-value-format.md)，generic 字段 schema 不证明所有字段可写。

---

## workflow list-state-transitions

查询工作项当前的完整工作流状态，包含所有节点 / 状态、当前位置、可流转方向。状态流流转前必须先调用此命令拿 `transition_id`。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `--project-key` | string | 是 | 空间 key |
| `--work-item-type-key` | string | 是 | 工作项类型 UUID（来自 `workitem meta-types`） |
| `--work-item-id` | number | 是 | 工作项 ID |
| `--flow-type` | number | 否 | 0=节点流，1=状态流；不传由后端自动检测 |

```bash
meegle workflow list-state-transitions \
  --project-key PROJ \
  --work-item-type-key 678de79dc62484dbfcc76150 \
  --work-item-id 12345 \
  --format json
```

返回路径以当前响应为准：历史文档使用节点流 `workflow_nodes[]`（`id` / `name` / `status` / `owners` / `fields`）、状态流 `state_flow_nodes[]` 与 `connections[]`（source → target、transition_id）。当前 inspect 仅证明参数；本地 workflow 测试含简化的 `state_flow_nodes`，未覆盖完整节点配置/connection 条目。不能将这些路径当作已验证的完整返回 schema；缺失或多义时停止并披露未获取的配置，不能猜 ID、首条目标或写入试探。

---

## workflow list-state-required

每次真实 `workflow transition` / `workflow transition-state` 前查询同目标的有效必填，不等失败才查。有效必填以该接口或当前节点/状态配置明确要求为依据；空值不等于必填，不因 fields/owners/排期为空强迫填写。未知口径需停止并请用户核对，不以副作用写入探测。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `--project-key` | string | 是 | 空间 key |
| `--work-item-id` | number | 是 | 工作项 ID |
| `--work-item-type-key` | string | 否 | 工作项类型 UUID；本 SOP 始终传已确认的类型，避免依赖未验证的推断 |
| `--node-id` | string | 否 | 节点流的 `node_id` 或状态流的目标 `state_key` |
| `--mode` | string | 否 | descriptor 明确示例 `unfinished` 为仅未完成必填；省略时的精确筛选语义未获取，不宣称默认全量 |

```bash
meegle workflow list-state-required \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-id 12345 \
  --node-id node_dev \
  --mode unfinished \
  --format json
```

返回证据边界：本地 `workflowRequiredInfo` fixture 仅有 `required_fields: []`，未证明非空条目的 `field_key` / `form_item_type` / 满足状态等完整结构；当前 descriptor 无返回 schema。必须按实际可解释的响应/配置识别有效必填、作用域和缺值，不能自造 required/is_required 字段或将解析失败当“无必填”。任一有效必填不可安全填写或缺用户真实值即阻塞，不能删字段继续。

---

## 节点字段配置（替代 meta-node-fields）

`workflow update-node` 修改节点的 owners / schedule / 自定义字段前需要确认合法 `field_key`。节点字段定义嵌在 `workflow list-state-transitions` 返回的 `workflow_nodes[].fields` 里。

```bash
meegle workflow list-state-transitions \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-id 12345 \
  --format json
```

仅在当前响应确有 `data.workflow_nodes[]` 时按唯一目标 `id` 读取 `fields`；字段/配置缺失时披露未知，不把示例路径硬套到其他响应。节点专属 owner 与排期不放入 `--fields`：统一排期 `--node-schedule` 为 object，差异排期 `--schedules` 为 array<object>，按 `different_schedule` 选择；不是节点表单 schedule 的 `{start_time,end_time}`。详见节点 SOP。

---

## 常见用法

以下是**已唯一定位目标且获用户授权**后的顺序示例，ID/字段均需替换为真实值。每次执行前读取当前状态和有效必填，缺值/歧义追问、不编造默认；预览不证明业务成功。示例均先 dry-run，核对目标、输入与用户/宿主授权后才去掉 `--dry-run` 实际执行一次。写后回读同空间/类型/工作项/目标节点或状态与本次补字段，exit code 0 不等于完成，回读不符/失败披露未验证或部分完成。

超时/断连/解析失败先只读核对，不能证明未落地则停止，不盲重试；权限拒绝停止当前业务目标全部后续操作。明确拒绝且确认无副作用才按 SOP 重核后有界修正。批量逐步预检/回读，前步未知或依赖阻塞时停止后续依赖流转，已确认结果单独汇报。

### 节点流：完成当前节点

```bash
# 1. 查节点
meegle workflow list-state-transitions \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-id 12345 \
  --format json
# 从返回 JSON 的 data.workflow_nodes[] 中读取 id、name、status 和 owners。

# 2. 检查必填项
meegle workflow list-state-required \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-id 12345 \
  --node-id node_dev \
  --mode unfinished \
  --format json

# 3. 确认必填已满足与授权后，预览 confirm
meegle workflow transition \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-id 12345 \
  --node-id node_dev \
  --action confirm \
  --dry-run \
  --format json
# 实际执行后按步骤1回读同目标状态/补字段，工作项字段另用 workitem get。
```

### 状态流：状态切换

```bash
# 1. 查可用 transitions
meegle workflow list-state-transitions \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-id 12345 \
  --format json
# 从返回 JSON 的 data.connections[] 中读取可用 transitions。

# 2. 拿到目标 state_key 后，检查必填
meegle workflow list-state-required \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-id 12345 \
  --node-id target_state_key \
  --mode unfinished \
  --format json

# 3. 确认必填已满足与授权后，预览状态切换
meegle workflow transition-state \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-id 12345 \
  --transition-id <transition_id> \
  --dry-run \
  --format json
# transition_id 必须是当前 connections 返回的 number，不是目标状态名。
# 实际执行后按步骤1回读同目标状态/补字段，工作项字段另用 workitem get。
```
