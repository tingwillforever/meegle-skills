# SOP: Update Work Item

> **CRITICAL** — 开始前先读 [`../SKILL.md`](../SKILL.md)（前置检查、授权流程、命令参数参考、字段值格式、通用规范和错误处理），以及本目录下的 [`error-handling.md`](error-handling.md)。

本 SOP 用于在飞书项目中更新工作项的字段值，全程自动化执行。**不包括状态/节点流转**（见 [`sop-transition-state.md`](sop-transition-state.md) / [`sop-transition-node.md`](sop-transition-node.md)）和**节点级字段**（见 STEP 4 边界）。

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

> **URL 处理**：用户给了 URL 必须先调 `meegle url decode --url '<URL>' --format json`。只有 `url_kind == workitem_detail` 才能进入本 SOP；其他 kind 按 [`url-kinds.md`](url-kinds.md) 拒绝或追问。拿到 `simple_name` 和 `work_item_id` 后，再用 `meegle space list --format json` 把 `simple_name` 转成权威 `project_key`（同名空间可能多个）。`url decode` 返回的 `work_item_type` 只是 `api_name`，**不是** `work_item_type_key`。**禁止**自己从 URL 截取路径段作参数，也不要把 `api_name` 直接当成 type key 传给业务命令。

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

> ⚠️ 本节下方旧 `转换规则` 表（标 stringified 的那部分）保留作为 `workitem update` 个别字段历史契约的兜底，仅在 [field-value-format.md](field-value-format.md) 的原生 shape 实测被后端拒绝时回退使用。`workitem create` 永远用原生 shape。

角色字段补充约束：

- `role_owners` 的 `field_value` 走 [field-value-format.md](field-value-format.md) 中的原生结构体数组
- 不要把“处理人”默认翻译成 `owner`
- 不要尝试直写 `current_status_operator`

🚨 **关键约定**：`workitem update` 里多数旧字段仍沿用 **STRING 协议层**，标量直接字符串化，很多数组/对象字段需要先 JSON.stringify；但像 `role_owners` 这类已经在 [field-value-format.md](field-value-format.md) 明确为**原生结构**的字段，优先按那里的原生 shape 传，不要强行 stringify。

| field_type_key | 转换规则 & field_value 传参 |
|---|---|
| `text` / `number` / `bool` / `link` | 直接字符串：`"100"` / `"true"` / `"https://..."` |
| `user` | 单个 userkey 字符串。**用户给姓名时** → 默认先用 `meegle user search --query "姓名" --project-key PROJ --format json`；若出现同名结果，展示候选 `email` / `user_key` 让用户确认 |
| `multi-user` | **stringified** 一维 userkey 数组：`"[\"key1\",\"key2\"]"` |
| `role_owners` | 结构体数组；按 [field-value-format.md](field-value-format.md) 的原生 shape 传 `[{\"role\":\"role_xxx\",\"owners\":[\"user_key\"]}]`，不要降级成 `owner`，也不要额外 JSON.stringify 这一层 |
| `select` / `radio` | 纯字符串 option_id：`"opt_xxx"` |
| `multi-select` | **stringified** 对象数组：`"[{\"option_id\":\"xxx\"}, {\"option_id\":\"yyy\"}]"` |
| `tree-select` | 纯字符串末级叶子的 option_id |
| `tree-multi-select` | **stringified** 字符串一维数组（**禁对象数组**）：`"[\"id1\",\"id2\"]"` |
| `multi-text`（富文本） | Markdown 字符串。语法见 [`rich-text-editor-markdown-syntax.md`](rich-text-editor-markdown-syntax.md) |
| `date` | 毫秒时间戳字符串：`"1722182400000"` |
| `schedule`（区间） | **stringified**：`"[1722182400000,1722268800000]"` |
| `precise_date` | **stringified**：`"{\"start_time\":1722182400000,\"end_time\":1722268800000}"` |
| `signal` | `"true"` / `"false"` / `"null"` 纯字符串 |
| `workitem_related_select` | 单个工作项 ID 字符串。某些空间要求 number、某些要求 string，**报类型校验失败时立刻切换格式重试** |
| `workitem_related_multi_select` | **stringified** ID 数组。**禁止写入自身 ID**（触发 `exists loop` 循环引用报错） |
| `file` / `multi-file` | 不走 `workitem update` 的 `field_value` 协议。改用 `meegle attachment upload --project-key X --work-item-type-key TYPE_KEY --work-item-id ID --field-key field_key --fileName a.pdf --file /absolute/path/a.pdf --format json` 直接上传并挂到该附件字段；需要删附件时用 `attachment delete`，需要下载时用 `attachment download` |

### STEP 4 — 执行更新

```bash
meegle workitem update \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-id 12345 \
  --update-fields '[{"field_key":"priority","field_value":"opt_high"},{"field_key":"name","field_value":"新标题"}]' \
  --format json
```

**注意 cli flag 名是 `--update-fields`（kebab）**，对应 mcp 协议的 `update_fields`（snake）。

`--update-fields` 是 **JSON 数组字符串**，每个元素是 `{"field_key":"...","field_value":"..."}`。多字段一并传：

```bash
--update-fields '[
  {"field_key":"name","field_value":"新标题"},
  {"field_key":"priority","field_value":"opt_high"},
  {"field_key":"role_owners","field_value":[{"role":"role_handler","owners":["7457914056381416309"]}]},
  {"field_key":"tags","field_value":"[{\"option_id\":\"tag_a\"},{\"option_id\":\"tag_b\"}]"}
]'
```

⚠️ 注意外层 JSON 字符串里嵌套的 `field_value` 内层 JSON 必须**双重转义**（`\"` 转 `\\\"`）。Bash 单引号包外层 → 内层就用 `\"`。

### STEP 5 — 确认结果

```bash
meegle workitem get \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-ids '[12345]' \
  --format json
```

回显修改后的字段值给用户。

---

## 增量追加（Append SOP）

⚠️ `workitem update` 是**覆盖语义**。当用户要"追加" / "添加" / "再加一个"时，必须：

**1. 先取旧值** —— `workitem get` 拿 `data[0].fields[].field_value`

**2. 按字段类型合并旧 + 新**：

| 字段类型 | 合并方式 |
|---|---|
| `text` / `multi-text` | 新文本拼接到旧文本后面（如换行后 append） |
| `multi-select` | 旧选项 + 新选项 → `[{"option_id":"x"}, {"option_id":"y"}, ...]` |
| `tree-multi-select` | 一维字符串数组 + 去重 → `["id1","id2"]` |
| `workitem_related_multi_select` | 旧 ID 数组 + 新 ID 数组 + 去重 |
| `multi-user` | 旧 userkey 数组 + 新 userkey 数组 + 去重 |
| `multi-file` | 追加附件时直接重复执行 `attachment upload` 即可；不要把附件字段当成 `workitem update --update-fields` 的 stringified JSON 覆盖写入路径 |

**3. 整体 stringify 后通过 `--update-fields` 覆盖写**。

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
| **模板切换**（修改 template 字段） | 高风险操作，**唯一需要主动确认**的场景。提醒用户切换模板会影响后续可见字段集。 |
| **循环引用** | 关联类字段写入前**必须排查当前工作项自身 ID**，禁止把自身 ID 写入关联项，否则触发 `exists loop`。 |

---

## 不可写入的字段类型

遇到时**直接跳过并告知用户**：

| 类型 | 原因 |
|---|---|
| `vote-boolean`（轻量表态） | 计数器，只能页面操作 |
| `vote-option` / `vote-option-multi`（投票） | 不支持接口写 |
| `compound_field` / `multi_user_compound_field`（复合明细表） | API 暂不支持 |
| 计算字段 | 系统自动算，只读 |

---

## 错误自愈（按报错特征匹配）

通用规则见 [`error-handling.md`](error-handling.md)。本 SOP 补充：

| 报错特征 | 自愈动作 |
|---|---|
| `need STRING type, but got: LIST/MAP` | 数组/对象忘了 JSON.stringify。把 field_value 转成字符串后重试。 |
| `cannot unmarshal object/array...` | 仅改格式（数字↔字符串、单值↔数组、对象↔字符串），值不变。 |
| `不满足层级配置`（级联层级） | `tree-select` / `tree-multi-select` 传了非末级。从 meta 的 `options.children` 树找叶子节点，**展示给用户选择**。 |
| `invalid select option(s)` | 枚举不合法。从 meta 的 `options[]` 模糊匹配 label，唯一匹配则修正重试，否则展示候选让用户选。 |
| `exists loop` | 关联字段写入了自身 ID。剔除自身后重试。 |
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
| 用户要改角色成员 | 明确告知"私有 cli 暂不支持，请到 web 端"，**不要尝试任何曲线方式** |
