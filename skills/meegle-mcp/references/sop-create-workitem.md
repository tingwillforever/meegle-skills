# SOP: Create Work Item

本 SOP 用于 direct MCP 下创建工作项。创建是真实写操作，必须先建模、preflight，再创建并 readback。

## 前置建模

创建前先明确：

- `project_key`
- 工作项类型描述或 `work_item_type_key`
- 标题
- 模板
- 必填字段和用户明确要求的可选字段
- 字段值来源
- 创建后如何核验

当前 session 只有一个 `projectKeys` 时，该值就是默认 `project_key`，直接回显并使用；不要再次追问空间。

## 执行顺序

1. `meegle.space.types`
   - 解析真实 `work_item_type_key`。
   - 不要把 api_name、中文名或页面路径当 type key。
2. `meegle.workitem.meta`
   - 读取字段、模板、options、字段类型。
   - 字段名只能映射到当前类型元数据中的 field key。
   - 用户指定处理人、报告人、项目经理等实例角色时，另调用一次 `meegle.config.flowRole.list`，按 [role-assignment.md](role-assignment.md) 解析。
3. `meegle.workitem.createPreflight`
   - 获取有效必填字段。
   - `createPreflight` 不是字段白名单；用户明确要求的可选字段仍要保留。
4. 构造 payload。
   - 角色-only 字段读 [role-assignment.md](role-assignment.md)；其他字段值读 [field-value-format.md](field-value-format.md)。
   - 关联字段名称转 ID 时读 [field-value-extras.md](field-value-extras.md)。
5. `meegle.workitem.create`
6. `meegle.workitem.get`
   - 回读新 ID、名称和关键字段。

## 字段规则

- option value 必须来自元数据，不使用 `"0"` / `"1"` 等示例值。
- 人名必须解析成 user key，同名时让用户确认。
- 关联字段必须写工作项 ID。
- 实例角色写 `role_owners`；不写 `current_status_operator`，不把角色语义降级成 `owner`。
- 隐藏/条件可见字段不要编造占位值；只有 preflight 或 create 明确要求时再让用户提供真实值。
- 不可 API 写入字段直接告知，不绕路。

## 批量创建

批量创建必须串行逐个调用 `meegle.workitem.create`，不要高并发。

每个创建结果都要单独记录 ID；失败项不得影响已成功项的 readback。

## 错误分流

- 字段 shape 错：回到 [field-value-format.md](field-value-format.md)。
- 必填字段缺失：重新 `createPreflight`，让用户补真实值。
- 字段非法：如果是有效必填，停止并说明元数据/preflight/create 契约不一致；如果是可选字段，可移除该可选字段后最多重试一次，并说明未写入。
- 权限不足：停止，不重试。

## 输出

创建成功后只在 readback 成功时说“已创建”。输出按 [result-display.md](result-display.md) 的 write readback 合同执行：

- 工作项 ID
- 名称
- 类型
- 已设置关键字段
- 未能写入的字段及原因
