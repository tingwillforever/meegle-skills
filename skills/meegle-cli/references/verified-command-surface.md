# Verified Command Surface

Use this file to choose the default-safe command path.

## Command Alignment Status

**⚠️ 核心主路径尽量与 upstream 对齐，但仍有少量差异**

当前 public CLI 优先暴露 upstream-compatible 主路径，并保留少量显式批准的私有扩展。以 `meegle inspect` 的 live 输出为准。

## Upstream Commands Support Status

| Upstream 命令 | 支持状态 | 说明 |
|--------------|---------|------|
| `space list` | ✅ 支持 | |
| `workitem create` | ✅ 支持 | |
| `workitem get` | ✅ 支持 | |
| `workitem update` | ✅ 支持 | |
| `workitem query` | ❌ 不支持 | 使用 `workitem search-by-params` / `workitem search-filter` 代替 |
| `workitem meta-types` | ✅ 支持 | |
| `workitem meta-fields` | ✅ 支持 | |
| `workitem meta-roles` | ✅ 支持 | |
| `workitem meta-create-fields` | ✅ 支持 | |
| `workflow transition` | ✅ 支持 | |
| `workflow transition-state` | ✅ 支持 | |
| `workflow update-node` | ✅ 支持 | |
| `workflow list-state-transitions` | ✅ 支持 | |
| `workflow list-state-required` | ✅ 支持 | |
| `workflow meta-node-fields` | ❌ 不支持 | MCP 无对应工具 |
| `user search` | ✅ 支持 | 姓名/关键字检索需带 `--project-key` |
| `team list-members` | ✅ 支持 | |
| `view list` | ✅ 支持 | |
| `view items` | ✅ 支持 | |
| `view create-fixed` | ✅ 支持 | |
| `view update-fixed` | ✅ 支持 | |
| `view delete` | ✅ 支持 | destructive；需要 `--confirm`，仅在用户明确要求删除视图时使用 |
| `view create-condition` | ✅ 支持 | |
| `view update-condition` | ✅ 支持 | |
| `chart get` | ✅ 支持 | 支持显式 `chart_id` 读取，也支持 chart URL decode 后路由 |
| `chart list` | ❌ 暂不开放 | 当前私有化版本后端未提供稳定可用 API，先停用 public surface |
| `workhour list-records` | ❌ 暂不开放 | 当前私有化版本空间内基本未开启实际工时，先停用 public surface |
| `workhour list-schedule` | ❌ 不支持 | MCP 无对应工具 |
| `attachment upload-file` | ✅ 支持 | 按 MCP 实际工具公开；适合富文本图片、通用文件上传 |
| `attachment upload` | ✅ 支持 | 按 MCP 实际工具公开；直接上传并挂到工作项附件字段 |
| `attachment download` | ✅ 支持 | 通过鉴权 HTTP stream 原子写入本地文件；支持 `--output` / `--output-dir` / `--force` |
| `attachment delete` | ✅ 支持 | destructive；需要 `--confirm`，仅在用户明确要求删除附件时使用 |
| `comment add` | ✅ 支持 | |
| `comment list` | ✅ 支持 | |
| `comment remove` | ✅ 支持 | destructive；需要 `--confirm`，仅在用户明确要求删除评论时使用 |
| `comment update` | ✅ 支持 | |
| `subtask create` | ✅ 支持 | |
| `subtask list` | ✅ 支持 | |
| `subtask update` | ✅ 支持 | |
| `mywork todo` | ❌ 不支持 | MCP 未提供 |

**覆盖率**: 36/42 = 85.7%

## Verified Commands

Prefer these by default:

### Project & Space
- `space list`
- `space detail`
- `space business-lines`
- `workitem meta-types`
- `team list-members`

### Work Item
- `workitem create`
- `workitem get`
- `workitem update`
- `workitem meta-create-fields`
- `workitem meta-fields`
- `workitem meta-roles`

### Workflow
- `workflow list-state-transitions`
- `workflow transition`
- `workflow transition-state`
- `workflow update-node`
- `workflow list-state-required`

### View
- `view list`
- `view items`
- `view create-fixed`
- `view update-fixed`
- `view delete`
- `view create-condition`
- `view update-condition`

### Chart
- `chart get` — 用户给 `chart_id` 时可直接读取；用户给 `chart_detail` / `view_chart` URL 时，先 `url decode` 再路由到该命令

### Attachment
- `attachment upload-file`
- `attachment upload`
- `attachment download`

### Comment
- `comment add`
- `comment list`
- `comment update`

### Subtask
- `subtask list`
- `subtask create`
- `subtask update`
- `subtask operate`

### User
- `user search`
- `user query` — 用于已知 `user_key` / `email` / `out_id` 的精确解析；姓名/关键词检索默认走 `user search`

### Private Extensions
- `workitem abort`
- `workitem restore`
- `workitem freeze`
- `workitem unfreeze`
- `workitem search-filter`
- `workitem search-by-params`
- `workitem list-op-records` — body 中 `project_key` 必须是 UUID（CLI 自动从 simple_name 转换，参考 `error-handling.md` Pitfall 10）；upstream spec 不接受 `work_item_type_key` 字段，但 CLI/MCP 仍要求该参数用于客户端授权范围判定，缺失会得到 `work_item_type_required`；额外可选过滤参数：`start_from`、`operator`、`operator_type`、`source_type`、`source`、`start`/`end`
- `user me`
- `release deploy-task-*`

## Conditional Commands

Allowed only after prerequisite discovery:

- `workflow list-state-required`
- `workflow transition-state`
- `workflow transition`
- `workflow update-node`
- `workitem abort`
- `workitem restore`
- `workitem freeze`
- `workitem unfreeze`
- `space detail`
- `attachment delete` destructive path: only after the user explicitly asks to delete attachments, requires `--confirm` to execute, and always warn that deletion is irreversible
- `comment remove` destructive path: only after the user explicitly asks to delete a comment, requires `--confirm` to execute, and always warn that deletion is irreversible
- `view delete` destructive path: only after the user explicitly asks to delete a view, requires `--confirm` to execute, and always warn that deletion is irreversible
- `release deploy-task-create`
- `release deploy-task-execute`
- `release deploy-task-apply-white-list`
- `release deploy-task-verify`

Use `meegle inspect <resource>.<method>` first and check the caveat.

## Unsupported Commands

| 命令 | 原因 | 替代方案 |
|------|------|---------|
| `chart list` | 当前私有化版本后端未提供稳定可用 API | 暂无稳定 public 替代；如需图表详情，仅在已知 `chart_id` 时使用 `chart get` |
| `workhour list-records` | 当前私有化版本空间内基本未开启实际工时 | 暂无稳定 public 替代；需要工时能力时改走页面或等待空间启用 |
| `mywork todo` | MCP 未提供 | 使用 `workitem search-by-params` / `workitem search-filter` 组合查询 |
