# SOP: Create Work Item

> **CRITICAL** — 开始前先读 [`../SKILL.md`](../SKILL.md)（前置检查、授权流程、命令参数参考）和 [`error-handling.md`](error-handling.md)。

本 SOP 用于在飞书项目中创建工作项（需求、任务、缺陷等），全程自动化执行。

> 与上游 SaaS 版的关键差异（私有 cli）：
> - **`role_owners` 可写，`current_status_operator` 不可写**：人员语义若本质上是实例角色（如处理人 / 项目经理 / 研发代表 / 测试代表），优先写 `role_owners`；`current_status_operator` 是系统根据当前流转单元引用的实例角色自动派生的字段，不能直接写。
> - **按姓名查 userkey** 默认只用 `meegle user search --query "姓名" --project-key PROJ --format json`；若出现同名结果，展示候选 `email` / `user_key` 让用户确认。
> - **模板 ID 是必填项**：创建时必须传 `--template-id`。

---

## 写操作建模

创建前先明确：

- 目标对象：空间、工作项类型、标题、模板。
- 目标字段：必填字段、用户明确要求的可选字段、字段值来源。
- 变更意图：为什么创建、是否临时验证、是否需要后续清理。
- 风险等级：通过 `inspect` 或 verified command surface 确认命令面；创建是真实写入，不套用读路径“最终查询一次”预算。
- 结果核验：创建成功后用 `workitem get` 回读 ID、名称和关键字段。

## 执行流程

### STEP 1 — 提取意图

从用户输入中提取：
- **空间名** — 哪个项目空间
- **工作项类型** — 需求 / 任务 / 缺陷 / 其他
- **字段值** — 标题、优先级、负责人、描述等
- **URL**（如有）— 先调 `meegle url decode --url '<URL>' --format json` 解析

如果用户提到的是“处理人 / 项目经理 / 研发代表 / 测试代表”这类角色语义，创建场景默认**按实例角色理解**，优先准备写入 `role_owners`；不要先把这类语义降级成 `owner`。

### STEP 2 — 确认空间和类型

1. 用 `meegle space list --format json` 验证空间 → 获取 `project_key`
2. 用 `meegle workitem meta-types --project-key PROJ --format json` 获取类型列表 → 确认 `work_item_type_key`

> 唯一匹配则直接用，多个匹配则展示列表让用户选，无匹配则问用户。**禁止猜测。**

### STEP 3 — 收集元数据

若当前命令面已提供 `workitem create-preflight`，在准备写入前优先用它评估有效必填字段：

```bash
meegle workitem create-preflight \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --name "TITLE" \
  --field-value-pairs '[...]' \
  --format json
```

读取返回的 `missing_required_fields[]` / `required_fields[]` 作为本次 create 需要补齐的有效必填字段。`source == "mcp_visibility_fallback"` 且 `confidence == "medium"` 时，说明这是 MCP 降级判断，最终仍以后端 create 结果为准。

`workitem create-preflight` 不是字段白名单：它只判断当前 payload 是否缺少有效必填字段。用户明确要求写入的非必填字段仍应按字段 shape 转换后保留在 `field_value_pairs` 中，再交给 `workitem create` 做最终校验；不要因为字段不在 `required_fields[]` / `missing_required_fields[]` 中就过滤掉。

`meta-create-fields` 仍用于字段发现、字段类型、模板和枚举值：

```bash
meegle workitem meta-create-fields \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --format json
```

从返回中提取：
- **模板列表**：找 `field_key == "template"` 的字段，读 `options[]` 获取可用模板
- **候选字段**：遍历 `.data[]`，读取 `field_key` / `field_name` / `field_type_key` / `is_required` / `is_visibility` / `options[]`
- **字段配置**：用户提到的字段的 `field_key`、`field_type_key`、`options`

⚠️ 不要误读返回结构：`meta-create-fields` 的真实返回是 `.data[]` 扁平字段数组，不是 `.data.fields[]`。

⚠️ 不要把 raw `meta-create-fields.is_required == 1` 当成最终必填清单。有效必填优先来自 `workitem create-preflight`；只有旧 CLI / no-preflight 路径才用 `is_required == 1 && is_visibility == 1` 做本地可见必填保护。`is_required == 1` 但 `is_visibility != 1` 的隐藏/条件可见字段不应由 CLI 主动强迫填写，交给 preflight / 后端 create 做最终校验。

### STEP 4 — 自动匹配模板

根据 STEP 3 获取的模板枚举值：
- **只有一个模板** → 自动选择
- **多个模板** → 根据用户描述中的关键词匹配最接近的模板名，选不出来时展示列表让用户选
- **用户明确指定了模板名** → 精确匹配

### STEP 5 — 构造创建 payload

优先采用 **preflight 有效必填策略**：

- 必传：`--name`，以及 `workitem create-preflight` 返回的 `missing_required_fields[]` / `required_fields[]` 中尚未提供的字段
- `field_key == "name"` 用 `--name`
- `field_key == "template"` 优先用 `--template-id`
- 其他必填字段用 `--field-value-pairs`
- no-preflight 路径 fallback：只把 `meta-create-fields` 中 `is_required == 1 && is_visibility == 1` 的字段作为 CLI 本地可见必填保护
- `is_required == 1 && is_visibility != 1` 的隐藏/条件可见字段不主动补占位值，除非用户明确提供、preflight 明确要求，或后端返回缺字段错误
- 可选字段仅在用户明确要求时追加；追加后即使不在 preflight 的必填列表中，也要保留到最终 create payload

推荐优先级：

1. 标题、模板
2. `workitem create-preflight` 返回的有效必填字段
3. 用户明确要求的可选字段，例如 `description`、`role_owners`
4. 未要求的可选字段不传

创建场景下如果用户指定了“处理人 / 项目经理 / 研发代表 / 测试代表”等角色人员：

- 优先把目标人写到 `role_owners`
- 不直写 `current_status_operator`
- `owner` 仅在用户明确要设置实例 owner，或该语义在当前类型上找不到对应 role 时才作为兜底字段

### STEP 6 — 转换字段值

🚨 **强制约束**：构造任何 `field_value` 前**必须先读** [field-value-format.md](field-value-format.md)，按 `field_type_key` 找到对应 shape 后再组装。**禁止**凭经验、记忆或别处 SOP 推断 shape；尤其禁止把数组/对象 `JSON.stringify` 再传（旧版 SOP 的 stringify 规则已废止）。不确定字段类型时先调 `meegle workitem meta-create-fields` 看 `field_type_key`。

**必填项缺失**时按下面顺序处理：
- 有用户输入 → 按字段类型转换后传入
- 没有用户输入但有合法默认值 → 仅在默认值来自元数据或业务约定明确时使用
- 人员类 / 关联类 / 业务域专用的可见必填字段缺值 → 询问用户，不要创建空必填字段的工作项
- 隐藏/条件可见必填字段缺值 → 不主动编造占位值；若 preflight 或后端明确返回缺字段，再向用户说明该字段被当前上下文最终校验要求
- 可见必填字段在 `workitem create` 中触发 `field [xxx] is illegal` → **优先怀疑 shape 不匹配**，回去查 [field-value-format.md](field-value-format.md) 重组而非删字段绕过

**值转换速查**：

| 来源 | 转换 |
|------|------|
| 字段 shape（select / multi_user / schedule / 富文本 / 关联字段 等任何类型） | 一律查 [field-value-format.md](field-value-format.md) |
| 人名 | 默认先用 `meegle user search --query "姓名" --project-key PROJ --format json`；若出现同名结果，展示候选 `email` / `user_key` 让用户确认 |
| 枚举值 | 从 `meta-create-fields` 的 `options[].value` 取真实 option_id；**禁止照搬官方文档示例的 `"0"`/`"1"`** |
| 日期 | 转为毫秒时间戳 |
| 关联字段名称→ID | 用 `search-filter`/`search-by-params` 解析后传 number（见 [field-value-extras.md](field-value-extras.md)）|

角色字段补充约束：

- `role_owners` 的 `field_value` shape 见 [field-value-format.md](field-value-format.md)；按原生结构体数组传入，不要改写成 `owner`
- `current_status_operator` 是系统字段，只能创建后由后端根据初始状态/初始节点引用的实例角色自动派生

### STEP 7 — 创建

```bash
meegle workitem create \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --name "标题" \
  --template-id 267706 \
  --field-value-pairs '[{"field_key":"priority","field_value":{"label":"P0","value":"option_1"}}]' \
  --format json
```

> `priority` 是 `select` 字段，必须传 `{label, value}` 对象，`value` 用 `meta-create-fields` 中 `options[].value` 的真实 option_id（不同租户不同）。其他 shape 见 [field-value-format.md](field-value-format.md)。

🚨 **批量创建**：当用户要求批量创建多个工作项时，必须**串行调用**（逐个请求），禁止高并发，以免触发平台限流。

### STEP 8 — 错误分流与降级

如果 `workitem create` 失败，按下面顺序处理：

- `field [xxx] is illegal`
  处理：先判断该字段是否来自 preflight 有效必填；no-preflight 路径再判断是否 `is_required == 1 && is_visibility == 1`
  - 若是有效必填 / 可见必填字段：停止，不要移除字段重试；说明这是创建页元数据或 preflight 与 create API 契约不一致
  - 若是可选字段：可移除该可选字段后重试一次，并在结果中说明该可选字段未写入
- 明确缺少模板
  处理：回到 STEP 3，读取 `field_key == "template"` 的 `options[]`
- 明确缺少某个字段
  处理：回到 STEP 3，优先跑 `workitem create-preflight`；如果 preflight 不可用，再核对所有 `is_required == 1 && is_visibility == 1` 字段。如果后端点名的是隐藏/条件可见字段，向用户说明这是后端最终校验要求，再让用户提供真实适用值

如果工作项已经创建成功：

- **不要**用删除必填字段的方式制造“创建成功”
- 若工作项是节点流（`pattern = Node`），改走 `workflow` 路径，在对应节点通过 `workflow transition --fields` / `workflow update-node` 补充
- 若字段明显不属于 workflow 可写范围，则告知用户改走 web 端

### STEP 9 — 确认结果

```bash
meegle workitem get \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-ids '[新ID]' \
  --format json
```

创建成功后，向用户展示：
- 工作项 ID 和名称
- 已设置的关键字段摘要

如果是临时验证项，当前 public CLI 不提供工作项删除命令；需要清理时先说明不能通过当前 CLI 自动删除，并让用户在 web 端或已批准的专用清理流程中处理。

---

## 不可写入的字段类型

遇到时**直接跳过并告知用户**：

| 类型 | 原因 |
|------|------|
| `file` / `multi-file`（附件） | 创建后再用 `attachment upload` 追加附件；当前创建接口不直接内联上传文件 |
| `vote-boolean`（轻量表态） | 计数器，只能页面操作 |
| `vote-option` / `vote-option-multi`（投票） | 不支持接口写 |
| `compound_field` / `multi_user_compound_field`（复合明细表） | API 暂不支持 |
| 计算字段 | 系统自动算，只读 |

---

## 错误自愈

通用规则见 [`error-handling.md`](error-handling.md)。本 SOP 补充：

| 报错特征 | 自愈动作 |
|---------|---------|
| `need STRING type, but got: LIST/MAP` | shape 不匹配；回查 [field-value-format.md](field-value-format.md) 找正确 shape，**禁止** JSON.stringify 绕过 |
| `json: unsupported type` / 网络超时 | 原参数直接重试 |
| 字段 key 不匹配 | 用 `workitem meta-create-fields` 全量返回按 `field_name` 模糊匹配 |
| `invalid select option(s)` | 从 meta 的 `options[]` 匹配；唯一匹配则修正重试，否则展示候选让用户选 |
| `field [xxx] is illegal` | 若字段是 preflight 有效必填，或 no-preflight 路径下的 `meta-create-fields.is_required == 1 && is_visibility == 1`，停止并报告元数据/preflight/create 契约不一致；若是可选字段，移除该可选字段后最多重试一次 |
| `不满足层级配置` | 查 `children` 树，展示末级叶子节点让用户选择 |
| 明确缺少必填字段 | 核对字段类型限制，关联工作项尝试数字↔字符串切换 |

若本轮失败与“处理人 / 项目经理 / 研发代表”等角色语义相关：

- 先确认是否应该写 `role_owners` 而不是 `owner`
- 再确认该工作项类型是否存在对应实例角色
- 不要通过直写 `current_status_operator` 规避

---

## 熔断条件

1. **工作项类型未找到** — `workitem meta-types` 失败超过 3 次
2. **字段转换大面积失败** — 转换失败比例 > 60%，终止流程并列出失败字段明细

---

## 常见问题

| 问题 | 处理 |
|------|------|
| 用户未指定空间 | 优先用 profile 默认 `project_key`，没有则问用户 |
| 用户未指定类型 | 如空间只有一种类型则直接用，否则问用户 |
| 用户提到的字段不存在 | `workitem meta-create-fields` 全量返回按 `field_name` 模糊匹配，找不到则告知用户 |
| 模板有多个 | 根据关键词匹配，匹配不到则展示列表让用户选 |
| 枚举值匹配不到 | 展示该字段所有枚举值让用户选 |
| 人名无法解析 | 告知用户提供 email 或 user_key |
