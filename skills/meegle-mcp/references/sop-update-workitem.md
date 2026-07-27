# SOP: Update Work Item

本 SOP 用于 direct MCP 下更新工作项字段。不包括状态/节点流转；状态流转读 [sop-transition-state.md](sop-transition-state.md)，节点流转读 [sop-transition-node.md](sop-transition-node.md)。

## 前置建模

更新前先明确：

- `project_key`
- `work_item_type_key`
- `work_item_id`
- 目标字段
- 目标值
- 语义是覆盖、追加、清空还是修正
- readback 字段

## 执行顺序

1. `meegle.workitem.get`
   - 确认目标工作项存在。
   - 追加类更新读取旧值。
2. 普通字段调用 `meegle.workitem.meta` 映射字段 key、字段类型和 options；角色-only 更新调用一次 `meegle.config.flowRole.list`，按 [role-assignment.md](role-assignment.md) 解析。
3. 构造更新 payload。
   - 角色-only 字段读 [role-assignment.md](role-assignment.md)；其他字段值读 [field-value-format.md](field-value-format.md)。
   - 关联字段名称转 ID 时读 [field-value-extras.md](field-value-extras.md)。
4. `meegle.workitem.update`
5. 必要时 `meegle.workitem.get` readback。
   - 最终回答按 [result-display.md](result-display.md) 的 write readback 合同输出目标、变更字段、回读证据和未完成项。

## 覆盖与追加

`meegle.workitem.update` 默认按覆盖语义理解。

用户说“追加”“加一个”“再加”“补充”时：

1. 先读取旧值。
2. 按字段类型合并旧值和新值。
3. 去重。
4. 用合并后的整体值更新。
5. readback 确认。

不要把追加误做覆盖。

## 高风险字段

下列字段更新后必须 readback：

- 关联字段
- 人员字段
- 排期/日期区间
- 多选字段
- 富文本
- 附件字段

附件字段优先走协作附件路径，不要把本地文件路径塞进普通字段值。

## 边界

- 实例角色通过 `role_owners` 可写；`current_status_operator` 不可写。节点 owner / workflow role 不属于本 SOP。
- 模板切换属于高风险操作，必须主动确认。
- 关联字段禁止写入当前工作项自身 ID。
- 节点表单字段不走工作项更新，切到节点 SOP。

## 错误处理

通用规则见 [error-handling.md](error-handling.md)。

同一字段 shape 修复最多重试 2 次；权限不足、hard-block 字段、目标对象不存在时停止。
