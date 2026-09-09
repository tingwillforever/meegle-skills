# SOP: Update Work Item

> **CRITICAL** — 开始前先读 [`../SKILL.md`](../SKILL.md)（前置检查、授权流程、命令参数参考、字段值格式、通用规范和错误处理），以及本目录下的 [`error-handling.md`](error-handling.md)。

本 SOP 用于在飞书项目中更新工作项的字段值，在用户与宿主授权范围内执行；本 SOP 不替代更严格的确认要求。**不包括状态/节点流转**（见 [`sop-transition-state.md`](sop-transition-state.md) / [`sop-transition-node.md`](sop-transition-node.md)）和**节点级字段**（见 STEP 4 边界）。

> 与上游 SaaS 版的关键差异（私有 cli）：
> - **`role_owners` 可写，`current_status_operator` 不可写**：如果用户要改的是实例角色成员，使用 `workitem update --update-fields` 写 `role_owners`；`current_status_operator` 是系统派生字段，不能直接写。
> - **附件操作**按 MCP 实际公开命令执行：上传通用文件走 `attachment upload-file`，工作项附件走 `attachment upload` / `attachment download` / `attachment delete`；详情见 [`attachment.md`](attachment.md)。
> - **按姓名查 userkey** 默认只用 `meegle user search --query "姓名" --project-key PROJ --format json`；若出现同名结果，展示候选 `email` / `user_key` 让用户确认。

---

## 写操作建模

更新前先明确：

- 目标对象：`project_key`、`work_item_type_key`、`work_item_id`。
- 目标字段：字段 key、字段类型、旧值读取需求、目标值。
- 变更意图：覆盖、追加、清空、修正，避免把追加误做覆盖。
- 风险等级：通过 `inspect` 或 verified command surface 确认命令面；复杂字段必要时保留写前读取和写后核验，不受读路径成本预算限制。
- 结果核验：更新成功后回读目标工作项，展示对象 ID、名称、变更字段和执行结果。

## 执行流程

### STEP 1 — 定位工作项并提取修改意图

从用户输入中提取：

- **目标工作项** — URL、工作项 ID 或名称
- **修改内容** — 哪些字段要改成什么值

如果用户明确说的是“项目经理 / 研发代表 / 测试代表 / 报告人”等具体角色名，优先按实例角色更新 `role_owners`。如果用户只说泛化词“处理人”，才需要再结合当前生效流转单元去解释它指向哪个实例角色。

> **URL 处理**：用户给了 URL 必须先调 `meegle url decode --url '<URL>' --format json`。只有 `url_kind == workitem_detail` 才能进入本 SOP；其他 kind 按 [`url-kinds.md`](url-kinds.md) 拒绝或追问。拿到 `simple_name` 和 `work_item_id` 后，直接把 `simple_name` 用于 `--project-key`；仅空间名称歧义或命令要求不同标识时发现，见 [workitem.md](workitem.md#发现与复用)。这不代表写权限，写前预校验不变。`url decode` 返回的 `work_item_type` 只是 `api_name`，**不是** `work_item_type_key`。**禁止**自己从 URL 截取路径段作参数，也不要把 `api_name` 直接当成 type key 传给业务命令。

🚨 **获取工作项类型（极重要）**：后续所有元数据查询都强依赖 `work_item_type_key`。如果用户没明确告知类型，**必须先调 `meegle workitem meta-types --project-key X --format json` 列出全部候选**，把 `api_name` (e.g. `story`) 翻译成真实的 UUID 形态 `work_item_type_key`（如 `678de79dc62484dbfcc76150`）。**绝不能猜测**类型 key。

🚨 **写前预校验**：拿到 `project_key + work_item_type_key + work_item_id` 后，先调一次：

```bash
meegle workitem get \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-ids '[12345]' \
  --format json
```

如果这里就报 `WorkItem Not Found`，先回查 `project_key` 或 `work_item_type_key`，不要直接继续 `workitem update`。

### STEP 2 — 查询字段配置

```bash
meegle workitem meta-create-fields \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --format json
```

返回所有字段的元数据数组（`field_key` / `field_name` / `field_type_key` / `options` / `is_required` / ...）。**不分页、一次性返回**，agent 应在一轮内拿完。

如果用户用的是字段中文名（如"优先级"、"问题类别"），从返回 array 里按 `field_name` 模糊匹配定位 `field_key`。

如果是 `select` / `multi-select` / `tree-select`：在同一返回里读 `options[].label` ↔ `options[].option_id` 映射。

### STEP 3 — 转换字段值

🚨 **首要约束**：构造 `field_value` 前**必须先读** [field-value-format.md](field-value-format.md)，按 `field_type_key` 找到对应 shape 后再组装。**禁止凭经验、记忆或本 SOP 旧版"必须 stringify"规则推断 shape**——那条规则已被官方文档覆盖（官方对 select / multi_select / schedule / 富文本 等结构化字段一律使用原生对象/数组）。

字段格式唯一来源是 [field-value-format.md](field-value-format.md)，不保留历史 STRING fallback。外层 `--update-fields` 参数是 JSON 编码的数组；内层 `field_value` 保持字段要求的原生类型，不能再次 stringify。

- 人名先用 `meegle user search --query "姓名" --project-key PROJ --format json` 解析；同名需用户消歧。
- `role_owners` 使用同空间、同类型的 `meta-roles` 与本次写前人员发现结果；更新前读取原值并保留非目标角色，追加时保留目标角色已有成员。
- `current_status_operator` 是派生字段，不可直写；节点 owner 需求走节点 SOP，不混用实例角色。
- 附件使用 [attachment.md](attachment.md) 的专用命令，不内联写附件字段。

### STEP 4 — 执行更新

```bash
meegle workitem update \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-id 12345 \
  --update-fields '[{"field_key":"priority","field_value":{"value":"opt_high"}},{"field_key":"name","field_value":"新标题"}]' \
  --format json
```

**注意 cli flag 名是 `--update-fields`（kebab）**，对应 mcp 协议的 `update_fields`（snake）。

`--update-fields` 是 **JSON 数组字符串**，每个元素包含 `field_key` 和按字段类型构造的 `field_value`。多字段一并传：

```bash
--update-fields '[
  {"field_key":"name","field_value":"新标题"},
  {"field_key":"priority","field_value":{"value":"opt_high"}},
  {"field_key":"role_owners","field_value":[{"role":"role_handler","owners":["7457914056381416309"]}]},
  {"field_key":"tags","field_value":[{"value":"tag_a"},{"value":"tag_b"}]}
]'
```

上面的 option / role / user 值均为占位，必须替换为本次目标元数据与人员响应中的真实值。Bash 单引号只包裹外层 JSON；不要把内层对象/数组转成带转义的字符串。

### STEP 5 — 确认结果

```bash
meegle workitem get \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-ids '[12345]' \
  --format json
```

逐项对比同空间、同类型、同 ID 回读的字段与用户预期；仅 exit code / err_code 0 不算完成。未持久化则报告未完成或部分完成及差异，不盲目再写；回读失败则报告“已提交但未验证”与无法确认字段。

---

## 增量追加（Append SOP）

⚠️ `workitem update` 是**覆盖语义**。当用户要"追加" / "添加" / "再加一个"时，必须：

**1. 先取旧值** —— `workitem get` 拿 `data[0].fields[].field_value`

**2. 按字段类型合并旧 + 新**：

| 字段类型 | 合并方式 |
|---|---|
| 文本 | 保留旧文本后追加；富文本结构按唯一格式索引处理 |
| 多选 / 多人员 / 多关联 | 按 [field-value-format.md](field-value-format.md) 的原生 shape 合并去重，保留旧值 |
| `role_owners` | 只调整目标角色；追加保留原成员并保留所有非目标角色 |
| 附件 | 使用 `attachment upload` 追加，上传结果未知时仍遵循错误处理的停止规则 |

**3. 将合并后的原生值放入字段数组，仅对外层 CLI 参数做 JSON 编码，然后覆盖写并回读核验**。

### 动态 MQL 追加

用户给自然语言条件（如"把名称含'依赖'的所有需求加到前置依赖字段"）时：

1. `meegle workitem search-by-params --project-key X --work-item-type-key T --search-group '{...}' --format json` 检索匹配项
2. 提取 ID 列表
3. 走【取旧值 → 合并 → 覆盖写】

> 私有 cli 没有 upstream 的 MQL 查询命令；用 `search-by-params`（field-level filters）或 `search-filter`（按名称模糊）替代。

---

## 边界

| 场景 | 处理 |
|---|---|
| **节点级字段**（节点排期、节点负责人、节点自定义字段） | **不属于本 SOP**，必须切到 [`sop-transition-node.md`](sop-transition-node.md) 或直接调 `meegle workflow update-node --project-key X --work-item-type-key T --work-item-id ID --node-id <node_id> --schedules '...' --node-owners '...'`。如检测到用户要改节点字段，自动切换。 |
| **实例角色成员更新** | ✅ 优先用 `workitem update` 写 `role_owners`；只有节点流/状态流本身要求改 node owner / role_assignee 时，才切到 workflow 路径。 |
| **状态流转 / 节点流转** | 不属于本 SOP。状态流走 [`sop-transition-state.md`](sop-transition-state.md)（`workflow transition-state`），节点流走 [`sop-transition-node.md`](sop-transition-node.md)（`workflow transition`）。 |
| **模板切换**（修改 template 字段） | 高风险操作，需要主动确认；其他写操作仍服从用户与宿主授权要求。提醒用户切换模板会影响后续可见字段集。 |
| **循环引用** | 关联类字段写入前**必须排查当前工作项自身 ID**，禁止把自身 ID 写入关联项，否则触发 `exists loop`。 |

---

## 不可写入的字段类型

遇到用户要求但不可写的字段先说明限制；只有用户同意部分执行后才能省略，最终逐项披露。格式与可写性以 [field-value-format.md](field-value-format.md) 为索引：

| 类型 | 原因 |
|---|---|
| `vote-boolean`（轻量表态） | 计数器，只能页面操作 |
| `vote-option` / `vote-option-multi`（投票） | 不支持接口写 |
| `compound_field` / `multi_user_compound_field`（复合明细表） | 写入可靠性未确认，优先页面维护，不自行承诺支持 |
| 计算字段 | 系统自动算，只读 |

---

## 错误自愈（按报错特征匹配）

通用规则见 [`error-handling.md`](error-handling.md)。本 SOP 补充：

| 报错特征 | 自愈动作 |
|---|---|
| `need STRING type, but got: LIST/MAP` | 停止猜测格式，查唯一格式索引与当前 descriptor；没有版本证据不切换 STRING 协议。 |
| `cannot unmarshal object/array...` | 先确认是否未发送/无副作用拒绝，再按已核验字段类型有界修正，禁止猜测类型轮试。 |
| `不满足层级配置`（级联层级） | `tree-select` / `tree-multi-select` 传了非末级。从 meta 的 `options.children` 树找叶子节点，**展示给用户选择**。 |
| `invalid select option(s)` | 枚举不合法。从 meta 的 `options[]` 模糊匹配 label，唯一匹配则修正重试，否则展示候选让用户选。 |
| `exists loop` | 关联字段写入了自身 ID。说明循环引用限制；不得擅自删除用户要求的关联项，先取得用户同意。 |
| 字段名匹配不到 | 用 `workitem meta-create-fields` 全量返回里的 `field_name` 模糊匹配 `field_key`。 |

---

## 熔断条件

通用规则见 [`error-handling.md`](error-handling.md)。本 SOP 补充：

1. **工作项类型未找到** — `workitem meta-types` 后仍无法定位、追问超过 3 次时停止
2. **字段值转换大面积失败** — 转换失败比例 > 60%，**终止流程**并列出全部失败字段明细让用户裁定

---

## 常见问题

| 问题 | 处理 |
|---|---|
| 用户没说工作项 | 追问 ID 或 URL |
| 字段名匹配不到 | `workitem meta-create-fields` 全量后按 `field_name` 模糊匹配 |
| 枚举值匹配不到 | 展示所有候选 option label / option_id 让用户选 |
| 用户给的是工作项名称（不是 ID） | `workitem search-filter --project-key X --work-item-name 关键词`，多结果时展示让用户选 |
| 用户要"追加"而非覆盖 | 走【增量追加 SOP】 |
| 用户要改节点字段 | 自动切到 `workflow update-node`，告知"这是节点级字段" |
| 用户要改角色成员 | 按已核验支持的实例角色写 `role_owners`；节点角色走节点 SOP，不写 `current_status_operator` |
