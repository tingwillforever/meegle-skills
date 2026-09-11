# 工作项读路径合同

## 目录

- [读路径建模](#读路径建模)
- [发现与复用](#发现与复用)
- [内置维度枚举小页查询](#内置维度枚举小页查询)
- [默认展示合同](#默认展示合同)
- [可读化优先级](#可读化优先级)
- [只读成本预算](#只读成本预算)
- [工作项对象结构](#工作项对象结构)
- [当前用户相关查询](#当前用户相关查询)
- [字段 projection 与本地输出裁剪](#字段-projection-与本地输出裁剪)
- [批量读取与分页硬上限](#批量读取与分页硬上限)
- [关联字段过滤](#关联字段过滤)
- [上下文推断](#上下文推断)
- [workitem meta-types](#workitem-meta-types)
- [workitem meta-create-fields](#workitem-meta-create-fields)
- [workitem create-preflight](#workitem-create-preflight)
- [常见用法](#常见用法)
- [富文本与描述图片（workitem get 默认返回 images）](#富文本与描述图片workitem-get-默认返回-images)

本文件覆盖工作项读路径、类型/字段元数据、展示映射和只读成本预算。创建、更新、流转等写操作只在对应 SOP 中执行。

## 读路径建模

执行工作项查询前，先在内部明确：

```text
查询主体：
筛选锚点：
过滤条件：
展示字段：
```

- 查询主体决定 `work-item-type-key`，也决定读取哪一个类型的 `meta-fields`。
- 筛选锚点用于缩小范围；关联字段过滤时，锚点工作项要先解析成数字 ID。
- 状态、负责人、优先级、业务线、时间范围通常是过滤条件，不要误判成查询主体。
- 字段 key、状态 value、枚举 option value 只来自同一类型的 `workitem meta-fields`；type key 只来自 `workitem meta-types`。

- “查询 A 的 B / A 下的 B / 关联到 A 的 B”通常以 B 为主体、A 为锚点。例：某项目下待讨论缺陷 → 主体=缺陷，锚点=项目，条件=待讨论。
- 先决定主体再选命令：基础名称/时间/状态/优先级/tag/业务线/相关用户等内置维度用 `search-filter`；自定义/关联字段、严格人员语义、复杂 AND/OR 用 `search-by-params`。两者都可表达时优先前者；服务端内部改写不改变此职责边界。
- 非工作项主体（视图、评论、子任务、流程、发布/部署）进入对应 reference，不套工作项元数据路径；命令能力不确定时按 [cli-guide.md](cli-guide.md#命令发现) 发现。

## 发现与复用

- `project_key` 即空间 key；已知 `project_key` / `simple_name` 直接传入，未指定时优先当前登录 profile / `auth whoami` 暴露的默认 key。只有中文名称、多空间无法判定或命令明确要求不同标识（如 UUID）时才用空间发现，不固定 `space list` / `space detail`。
- type key 必须来自 `meta-types`，精确/模糊匹配规则见 [workitem meta-types](#workitem-meta-types)。URL 的 api_name 必须经同空间 `meta-types` 映射，不能直接试探业务命令。
- 字段 key、状态/枚举 value 从主体类型的 `meta-fields` 获取；查询元数据不以 `meta-create-fields` 替代，创建/写入则服从 SOP 的目标元数据/preflight。
- 只复用**同一任务、同 profile/账号/空间/类型**已取得且仍适用的证据，不复用历史 case 或跨类型字典。profile、账号、空间、类型改变，或观察到 schema 过期/漂移时，重新读取相应权威证据；不会因此取消 URL type 映射或写前/写后核验。
- 不缓存授权结论，已知空间/元数据不等于有权写入。权限硬停优先于发现、fallback 和恢复，见 [error-handling.md](error-handling.md#数据权限硬停错误)。
- `inspect`、只读 `--dry-run` 条件只在 [cli-guide.md](cli-guide.md#命令发现) 定义；以下示例是证据尚未获取时的顺序，不要求同 scope 重复发现。

## 内置维度枚举小页查询

当用户要求“不同 X 各最新 N 条 / 每个 X 展示 N 条 / 按 X 分组列出前 N 条”，并且 `X` 是 `workitem search-filter` 已支持的内置维度时，把每个维度值当成独立小页 bucket：

```bash
meegle workitem search-filter \
  --project-key PROJ \
  --work-item-type-keys '["TYPE_KEY"]' \
  --work-item-status '[{"state_key":"STATUS_VALUE"}]' \
  --output-select id,name,work_item_status,created_at \
  --page-size N \
  --format json
```

`--page-size` 上限为 **200**（实测 200 可用，超过则报错）。`search-filter` 只返回内置字段，把业务字段写进 `--output-select` 不会报错但也不会返回；具体边界见 [批量读取与分页硬上限](#批量读取与分页硬上限)。

状态 value 仍来自同一次 `meta-fields` 中 `work_item_status.options[].value`，展示时用同一份 options 映射回 label。`--work-item-status` 的对象形态以 live `inspect workitem.search-filter` 和已验证 CLI contract 为准；当前可用 `state_key` 传状态 value。优先用 `search-filter` 内置 flag 表达 `status`、`priority`、`business`、`tag`、`user_keys` 等维度，不要为了分 bucket 升级到 `search-by-params`。

这个规则适用的是“小页列表读取”，不是聚合统计。它的目标是每个 bucket 各取 N 条，所以允许对不同 bucket 各执行一次最终列表查询；同一 bucket 成功后不要再用相同条件重跑或扩大分页。若当前任务需要分布判断、总量判断或分页整体视角，直接读取每个 bucket 返回里的 `pagination.total`，不要只看当前页 `data.length`。

不适用场景：

- 严格负责人字段语义（如“当前负责人是我”）：走字段级人员条件的 `search-by-params`。
- 自定义字段、关联字段、复杂 AND/OR、嵌套条件：走 `search-by-params`。
- 用户要求全局排序后再分组，或要求每个状态的总数 / 聚合统计：按对应统计或分页策略处理，不套用小页 bucket。
- `search-filter` 当前 live contract 不支持该维度 flag：先 `inspect` 确认，再改用 `search-by-params`。

bucket 查询完成后，默认展示仍走统一可读化 gate：若列表页缺 `current_status_operator`，把当前展示页所有 ID 汇总后最多一次 `workitem get --fields '["current_status_operator"]'` 补负责人；当前页人员 raw key 汇总后最多一次 `user query` 回填姓名。

## 默认展示合同

用户没有指定展示字段时，工作项列表默认展示：

| 展示列 | 数据来源 |
|---|---|
| `ID` | 顶层 `id` |
| `名称` | 顶层 `name` |
| `当前状态` | 见下方状态可读化优先级 |
| `当前负责人` | 从 `fields[]` 中 `field_key` / `field_alias` 为 `current_status_operator` 的字段读取，见下方人员可读化优先级 |
| `创建时间` | 顶层 `created_at` 毫秒时间戳，见下方时间可读化规则 |

默认展示不能降级成只列 `ID + 名称`。只要最终查询返回了默认字段，就必须在最终回答中展示 `当前状态`、`当前负责人`、`创建时间`。

默认只展示前 `10` 条。若结果包含 `pagination.total`，说明“共命中 N 条，当前先展示前 10 条”；只有用户明确要求“继续 / 更多 / 全部 / 导出”时，才继续分页或扩大输出。若当前任务需要总量、分布或整体视角，直接读取返回里的 `pagination.total/page_num/page_size`；若输出里没有 `pagination`，先确认该响应原本是否就不带分页元信息，或是否还在使用旧版本产物，不要据此判断后端没有总数。

默认展示字段只适用于查询主体的最终读取，不适用于筛选锚点 lookup。

锚点 lookup 用来拿被关联工作项 ID，命令形状固定为：

```bash
meegle workitem search-filter \
  --project-key PROJ \
  --work-item-type-keys '["ANCHOR_TYPE_KEY"]' \
  --work-item-name "目标名称" \
  --output-select id,name \
  --page-size 10 \
  --format json
```

锚点 lookup 不要传 `--query` / `--keyword` / `--select`，也不要要求状态、负责人、创建时间。

主体最终查询必须显式取这些字段：

```text
id,name,work_item_status,current_status_operator,created_at
```

这里的“显式取”是返回字段声明，不代表这些字段都在同一层读取。`id`、`name`、`work_item_status`、`created_at` 属于稳定顶层字段；`current_status_operator` 属于 `fields[]` 业务字段，按 `field_key` / `field_alias` 读取。`search-filter --output-select current_status_operator` 不保证返回负责人字段。若默认展示页通过 `search-filter` 已拿到 `ID` / `名称` / `状态` / `创建时间`，但没有负责人字段，不要标记“未返回”；用当前页 ID 一次性补取负责人：

```bash
meegle workitem get \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-ids '[ID1,ID2]' \
  --fields '["current_status_operator"]' \
  --format json
```

这个补取只限当前展示页和默认展示必需字段，属于展示 gate，不是重跑同条件列表查询。若用户明确要求不展示负责人，或明确要求 raw / 不回填，则不要补取。

可额外取 `current_nodes` / `priority` 等场景字段，但字段位置仍按下方对象结构判断：`current_nodes` 是顶层字段，`priority` 是 `fields[]` 业务字段。不要用 `current_nodes` 替代 `work_item_status`。状态流工作项常见 `current_nodes=[]`，此时只能靠 `work_item_status.state_key` + `meta-fields work_item_status.options[]` 映射成可读状态。

## 可读化优先级

状态必须可读，但不得为了展示无限补查：

1. 若本轮已读取同一工作项类型的 `meta-fields`，复用其中 `field_key == "work_item_status"` 的 `options[]` 建立 `value -> label` 映射。
2. 若状态字典缺失或无法匹配，保留原始状态值并标注“状态未映射”；`current_nodes[].name` 可单列“当前节点”，不能冒充状态 label。
3. 若以上都不可用，展示 raw `work_item_status.state_key` / value，并标注“原始状态值”。

只要本轮已读到 `work_item_status.options[]`，最终展示状态必须使用 `options[].value -> options[].label` 映射，不能再用 `current_nodes[].name` 覆盖，也不能展示 raw `started`、`In Progress`、`tmrqE6oMg`、`-KFJXzaWr` 等值。无法匹配的状态标为未知/未映射；节点名单列，不覆盖状态。

`current_nodes=[]` 不代表状态不可读。对状态流工作项，如果已读 `meta-fields` 但无法把 `state_key` 映射成 label，回答前先检查是否取错工作项类型、是否裁剪掉 `work_item_status.options[]`，或是否读错字段；核对后仍无法匹配则明确标注“状态未映射”，不得猜测。

`meta-fields` 输出很大时，第一次就用 `--output-select field_key,field_name,field_alias,field_type_key,options` 窄读字段定义；仍然只算同一次权威元数据读取。不要先读完整元数据，再用第二条 `meta-fields | jq`、`meta-fields | rg`、`meta-fields | grep`、`meta-fields | sed`、`meta-fields | head` 或另一条 `meta-fields --output-select ...` 重新抽取。

需要精确状态 label 且输出可能很大时，必须在第一条且唯一一条 `meta-fields` 直接接 Python JSON reducer；其它已知具体字段名的场景可在首次读取时选用，避免终端显示大 JSON 后再补跑第二条业务命令。必须在第一次 `meta-fields` 就决定是否使用 reducer；不要先跑普通 `meta-fields`，再跑 `meta-fields | python3`。这个 reducer 只能裁剪当前这次 `meta-fields` 的返回，不得再次调用 `meegle`：

```bash
meegle workitem meta-fields \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --output-select field_key,field_name,field_alias,field_type_key,options \
  --format json |
python3 -c 'import json,sys
target="目标状态名"
d=json.load(sys.stdin)
rows=[]
wanted={"work_item_status","current_status_operator"}
owner_names={"负责人","当前负责人"}
for f in d.get("data", []):
    if f.get("field_key") == "work_item_status":
        g=dict(f)
        g["options"]=[o for o in f.get("options", []) if o.get("label")==target or o.get("value")==target]
        rows.append(g)
    elif f.get("field_key") in wanted or f.get("field_alias") in wanted or f.get("field_name") in owner_names:
        rows.append(f)
print(json.dumps({"data": rows}, ensure_ascii=False, indent=2))'
```

执行这个 reducer 后，后续必须从它的输出中取状态 value、状态 label 和负责字段 key；不要再跑普通 `meta-fields` 或另一条更窄的 `meta-fields --output-select field_key,options`。

如果没有按状态筛选，只是默认展示当前页状态，不要过滤 `work_item_status.options[]`，应保留完整 options 作为状态字典：

```bash
meegle workitem meta-fields \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --output-select field_key,field_name,field_alias,field_type_key,options \
  --format json |
python3 -c 'import json,sys
d=json.load(sys.stdin)
wanted={"work_item_status","current_status_operator"}
rows=[]
for f in d.get("data", []):
    if f.get("field_key") in wanted or f.get("field_alias") in wanted:
        rows.append(f)
    elif f.get("field_type_key") in {"workitem_related_select","work_item_related_select","workitem_related_multi_select","work_item_related_multi_select"}:
        rows.append(f)
print(json.dumps({"data": rows}, ensure_ascii=False, indent=2))'
```

回答前必须从这份输出构建 `status_label_by_value`，例如 `started -> 待修复`、`-KFJXzaWr -> 待验证`。不能把 raw value 直接写给用户。

人员默认尽量可读，也必须有界：

1. 优先复用查询结果字段里的 `label` / `name` / `display_name`。
2. `current_status_operator` 按 `fields[]` 字段处理，通过 `field_key` / `field_alias` 读取 `field_value`；不要只在顶层找负责人。
3. 如果 `search-filter` 默认展示页没有返回 `current_status_operator`，但已经拿到当前页 ID，用一次 `workitem get --work-item-ids '[...]' --fields '["current_status_operator"]'` 补取当前页负责人字段。
4. 如果当前展示页只有 `user_key`，且用户没有明确要求 raw / 不回填，可以收集当前页唯一 user_key，最多执行一次 `meegle user query --user-keys '["USER_KEY"]' --format json` 批量回填。
5. 如果用户明确说不要回填姓名，或 `user query` 不可用/失败，展示 raw `user_key` 并标注“原始 user_key”。
6. 不要逐条查人、不要扫描团队成员全集、不要跨页预取人员。

时间默认必须准确可读：

- `created_at` / `updated_at` 是 Unix epoch 毫秒时间戳，不是秒。
- 默认展示时使用 `Asia/Shanghai` 时区格式化为本地时间；不要心算或手工推导时间。
- 允许对当前展示页时间戳执行一次本地 `node` / `python3` 转换；这是本地确定性整理，不是业务重查，也不违反“不要重跑业务命令”。
- 若不运行本地转换命令，就直接用毫秒时间戳或 ISO 时间；不要输出未验证的人类时间。

示例：

```bash
node -e 'const ts=[1780544677296,1780381313574];
for (const t of ts) {
  console.log(new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
    hour12: false
  }).format(new Date(t)))
}'
```

## 只读成本预算

以下“一次”按同任务、同 scope、同展示页且证据仍适用计数（见 [发现与复用](#发现与复用)），不是全局缓存或权限缓存。禁止的是为相同结果重新查询/格式化，不禁止用户明确要求的分页、当前页必要字段补取或 [图片降级](#生效前提与降级)。若输出截断，先继续读取宿主已保留的本次输出；仍无法取得完整证据时按 [error-handling.md](error-handling.md) 披露/诊断，不把截断当业务失败盲重试，也不声称已完成。此处不新增本地解析、落盘或 reducer 授权。

- 同一业务目标最终列表查询只执行一次：`search-filter`、`search-by-params`、`view items -> workitem get` 成功后，只能本地映射、裁剪、排序和格式化。
- 内置维度枚举小页查询按 bucket 计数：同一 bucket 成功一次后只能本地整理；不同维度值各取 N 条时，可以各执行一条 `search-filter --page-size N`，但不要再对任一 bucket 做 probe、fallback 或扩大分页。
- 工作项列表查询若使用本地 `--output-select`，且任务关心总量、分布或分页整体视角，直接读取返回里的 `pagination.total,pagination.page_num,pagination.page_size`。若需要同时显式约束记录字段和分页字段，可以继续写 `data.<field>` 与 `pagination.xxx` 的组合路径。
- 同一工作项类型最多一次 `meta-fields`。需要状态/枚举/负责人字段映射时，第一次就用 `--output-select field_key,field_name,field_alias,field_type_key,options` 窄读；后续只从当前命令返回中提取状态 options、负责人字段、优先级 options、关联字段 key；不要为了“保存/解析”而重跑 `meta-fields`。
- 若默认展示页的列表结果缺少 `fields[]` 中的 `current_status_operator`，允许对当前页 ID 执行一次 `workitem get --fields '["current_status_operator"]'` 补取负责人字段；这不是第二次同条件列表查询，禁止扩大到全量分页。
- 同一展示页最多一次 `user query`，且仅用于当前页人员 raw key 回填。
- 最终查询成功后，回答前必须执行本地 gate：`当前状态` 没有可读 label 时先从已读 `meta-fields` 映射；`当前负责人` 缺失但可通过当前页 ID 补 `fields[]` 时先补 `workitem get`；`当前负责人` 只有 raw user_key 时先做一次当前页 `user query`。这些 gate 不属于重复最终列表查询。
- 普通只读查询默认不用 `--dry-run`；复杂新 shape、时间边界、排障按 [cli-guide.md](cli-guide.md#命令发现) 预览，不先跑 probe / sample query。
- 默认 `10` 条展示页通常直接从命令返回 JSON 中整理表格；但 `created_at` / `updated_at` 毫秒时间戳转换可以用一次本地 `node` / `python3`，不要心算。
- 大型 `meta-fields` 是例外：需要精确状态 / 枚举 option 时，可以在唯一一次 `meta-fields` 后接 Python JSON reducer 缩小输出；但 reducer 不得再次调用 `meegle`，也不得成为第二条 `meta-fields`。
- 业务 `meegle` 命令与本地 `jq` / shell 格式化分开执行。不要把取数和格式化写进同一个 shell。默认展示页不要把 `meegle` 业务命令重定向到 `/tmp`；若非默认展示场景确实要本地处理，只能处理已有业务结果，不要重跑业务命令。
- 不要为了从 `meta-fields` 抽取 `work_item_status` 或负责人字段，执行第二次 `meta-fields` 命令，也不要把同一份元数据写到 `/tmp` 或通过 `jq` / `rg` / `grep` / `sed` / `head` 管道再解析；从第一次返回中直接读取。

---

# 工作项元数据命令

查询工作项类型、字段、角色配置的辅助命令。在 `workitem get` / `workitem search-filter` / `workitem search-by-params` / 写操作 SOP 之前用来确认合法 key。

所有 workitem meta 命令已与 upstream 完全对齐：
- `workitem meta-types` — 列出空间下所有工作项类型
- `workitem meta-fields` — 列出字段配置（可按工作项类型过滤）
- `workitem meta-roles` — 列出流程角色配置（role key 在返回的 `id` 字段，显示名在 `name`；见 [用户可读展示](#用户可读展示)）
- `workitem meta-create-fields` — 获取创建工作项所需的元数据
- `workitem create-preflight` — 写入前评估当前 payload 缺少的有效必填字段（只读，不创建工作项）

查询/过滤/展示映射默认使用 `workitem meta-fields`。`workitem meta-create-fields` 是创建页元数据，只在创建工作项、字段 shape、模板/枚举或创建 API 报错自愈时使用；不要用它代替查询字段配置。创建时有效必填字段优先看 `workitem create-preflight`，不要直接把 raw `meta-create-fields.is_required == 1` 当成必须填写的最终清单。

空间/type 发现与复用统一见 [发现与复用](#发现与复用)。

---

## 工作项对象结构

`workitem get` / `workitem search-filter` / `workitem search-by-params` 返回的工作项对象按两层读取。后端 payload 未来可能增加其它 metadata，但 skill 展示和字段读取只依赖下方 allowlist；不在 allowlist 内的业务语义字段一律按 `fields[]` 处理。

**稳定顶层字段 allowlist**（可直接访问，不在 `fields[]` 里）：

| 字段 | 说明 |
|------|------|
| `id` | 工作项 ID |
| `name` | 标题（即工作项名称） |
| `current_nodes` | 当前所在节点数组，可能为空 `[]`；每项含 `id`、`name`、`owners` |
| `work_item_status` | 当前状态对象，含 `state_key`（如 `"started"`、`"Finished"`）；**无 display name 字段**。展示给用户时按上方状态可读化优先级处理：复用已读 `meta-fields` 的 `options[]`，未匹配时标注“状态未映射”；`current_nodes[].name` 仅单列当前节点。 |
| `created_at` | 创建时间（毫秒时间戳） |
| `updated_at` | 更新时间（毫秒时间戳） |
| `created_by` | 创建人 user_key |
| `updated_by` | 更新人 user_key |
| `deleted_at` | 删除时间（毫秒时间戳；未删除通常为 `0`） |
| `deleted_by` | 删除人 user_key |
| `work_item_type_key` | 工作项类型 UUID |
| `project_key` | 空间内部 ID，不等同于用户输入的 `simple_name` |
| `simple_name` | 空间 key / URL 中常见的 `project_key` 参数值 |
| `pattern` | 工作项流程模式，例如 `State` |
| `sub_stage` | 当前子阶段 / 状态原始值；展示仍优先使用 `work_item_status.options[]` |
| `template_id` | 模板 ID |
| `template_type` | 模板类型 |
| `fields` | 业务字段容器数组，不是业务字段本身 |
| `images` | 仅 `workitem get` 随 server 版本返回的富文本图片 uuid 摘要，结构/任务分流/旧版降级见 [富文本与描述图片](#富文本与描述图片workitem-get-默认返回-images) |

**`fields[]` 业务字段**：通过 `field_alias` 或 `field_key` 访问。包括但不限于 `current_status_operator`、`priority`、`business`、`owner`、`watchers`、`role_owners`、`description`、`template`、`field_*`、截止日期、关联字段、枚举字段等。

> 取标题用 `item['name']`，不要在 `fields[]` 里找。取当前负责人用 `fields[]` 里的 `current_status_operator`，不要在顶层找。`current_nodes` 可能为空数组，访问前先判断长度。

### 状态中文名映射

完整规则见 [可读化优先级](#可读化优先级)：只复用同类型 `work_item_status.options[]`；未匹配标注“状态未映射”，节点只能单列，不能替代状态。不要用 `workflow list-state-transitions` 查询列表展示 label。

### 示例：待讨论缺陷 + 中文状态名 + 原始负责人 user_key

当任务是“查缺陷管理里待讨论缺陷，展示标题、状态、负责人，负责人只需要 raw user_key”时，按读路径合同执行：

```bash
meegle workitem meta-types --project-key PROJ --format json
meegle workitem meta-fields \
  --project-key PROJ \
  --work-item-type-key BUG_TYPE_KEY \
  --output-select field_key,field_name,field_alias,field_type_key,options \
  --format json |
python3 -c 'import json,sys; target="待讨论"; d=json.load(sys.stdin); rows=[];
for f in d.get("data", []):
    if f.get("field_key") == "work_item_status":
        g=dict(f); g["options"]=[o for o in f.get("options", []) if o.get("label")==target or o.get("value")==target]; rows.append(g)
    elif f.get("field_key")=="current_status_operator" or f.get("field_alias")=="current_status_operator" or f.get("field_name") in {"负责人","当前负责人"}:
        rows.append(f)
print(json.dumps({"data": rows}, ensure_ascii=False, indent=2))'
meegle workitem search-by-params \
  --project-key PROJ \
  --work-item-type-key BUG_TYPE_KEY \
  --search-group '{"conjunction":"AND","search_params":[{"param_key":"work_item_status","operator":"HAS ANY OF","value":["STATUS_VALUE"]}],"search_groups":[]}' \
  --select id,name,work_item_status,current_status_operator \
  --page-size 10 \
  --format json
```

规则：
- `BUG_TYPE_KEY` 来自 `meta-types`；`STATUS_VALUE` 来自同一次 `meta-fields` 的 `work_item_status.options[]`。
- 负责人优先从最终查询结果 `fields[]` 中读取 `field_key` / `field_alias == "current_status_operator"`。
- 默认使用 `--select id,name,work_item_status,current_status_operator` 表达字段 projection，默认展示前 10 条。
- 结果直接基于返回 JSON 手工整理呈显，严禁为格式化而重复执行查询或在同一命令中管道串联 `jq`。

### 用户可读展示

状态、人员、毫秒时间、前 10 条和分页披露统一见 [默认展示合同](#默认展示合同) 与 [可读化优先级](#可读化优先级)，不在此重复维护。其它字段：

- `select` / `multi-select` / `tree-select` 等优先展示 label，未取得映射明确标注原始 key。
- 业务线名称可参考 `auth whoami` 的 `business_line_names`（仅只读 fallback 上下文，不代表普通工作项可见范围）；完整名称映射来自 `space business-lines`。
- 角色名称来自 `workitem meta-roles --project-key PROJ --work-item-type-key TYPE_KEY`。**该接口把 role key 放在 `id` 字段**（如 `"id": "role_065f31"`），显示名在 `name`，别名在 `role_alias`；据此才能把 `role_owners[].role` 反查成可读角色名。不要去找 `role_key` / `role_id`，它们不存在。
- 人名/关键词解析优先 `user search --query "姓名" --project-key PROJ`；精确 user_key 回填见上方 gate 与 [verified-command-surface.md](verified-command-surface.md)。只有任务明确为“空间下团队成员”才用 `team list-members`；团队列表及其 `user_keys` / `administrators` 不是空间成员全集，不用于扫描所有负责人。

---

## 当前用户相关查询

当用户说“我的”“我参与的”“与我相关的”某类工作项时，不能直接查询该类型全量列表。

- 若使用 `workitem search-filter`，必须显式加 `--user-keys '["<meegle_user_key>"]'`。`--user-keys` 匹配 creator / follower / role owner，语义是“与这些用户相关的工作项”。
- 不带 `--user-keys` 的查询，只能解释为“空间内该类型工作项列表”，不能默认解释为“当前用户相关列表”。
- 若用户要求更严格的字段级人员语义，如“我负责的”“people 字段包含我”，改用 `workitem search-by-params` 的 `people` 条件或对应字段条件。
- 当前登录用户的 `meegle_user_key` 优先来自 `meegle auth whoami --format json`；不要用 `user query --user-keys '["current_login_user()"]'` 替代字段级过滤身份发现。

### 严格负责人字段过滤

“我负责的”“当前负责人是我”不是宽泛的“与我相关”。推荐路径：

```bash
meegle auth whoami --format json
meegle workitem meta-types --project-key PROJ --format json
meegle workitem meta-fields \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --output-select field_key,field_name,field_alias,field_type_key,options \
  --format json
meegle workitem search-by-params \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --search-group '{"conjunction":"AND","search_params":[{"param_key":"OWNER_FIELD_KEY","operator":"HAS ANY OF","value":["USER_KEY"]}],"search_groups":[]}' \
  --format json
```

其中 `OWNER_FIELD_KEY` 和优先级枚举 value 来自同一次 `meta-fields`。这个路径复用同一次 `meta-fields` 的 `work_item_status.options[]` 映射状态；无法匹配则标为未映射，节点名不得覆盖状态，也不要重复抽取同一元数据。不要先试 `search-filter --user-keys` 再自愈；它覆盖 creator / follower / role owner，不能表达严格负责人字段语义。

这是只读路径，已验证的普通字段条件直接执行；新复杂嵌套条件、时间边界、shape 不确定或排障时按 [cli-guide.md](cli-guide.md#命令发现) 预览，不因“我负责”固定 dry-run。

同一 case 中不要先跑一个 `page-size 1` / sample probe 查询，再跑第二个正式分页查询。负责人字段、状态字段和优先级条件都应该在一次最终查询中完成；表格直接基于这次返回 JSON 手工整理，不与业务命令串接本地格式化管道。

对 “我负责的高优先级产品需求，只要标题、状态和负责人” 这类查询，推荐的最小序列是：

1. `meegle auth whoami --format json`
2. `meegle workitem meta-types --project-key PROJ --format json`
3. `meegle workitem meta-fields --project-key PROJ --work-item-type-key TYPE_KEY --output-select field_key,field_name,field_alias,field_type_key,options --format json`
4. `meegle workitem search-by-params --project-key PROJ --work-item-type-key TYPE_KEY --search-group ... --select id,name,current_nodes,work_item_status,OWNER_FIELD_KEY,priority --page-size 10 --format json`

规则补充：
- 第 3 步同一份 `meta-fields` 提取负责人字段 key、优先级 option value 及状态 `value → label` 映射。
- 第 4 步为最终查询，默认用 `--select` 声明所需字段，展示总数直接读取 `pagination.total`。
- 最终 5 列呈现直接基于返回数据手工整理，严禁为格式化而重发业务查询或管道串接本地脚本。

---

## 字段 projection 与本地输出裁剪

工作项读取场景里有三种容易混淆的字段选择能力：

| 能力 | 使用方式 | 适用场景 |
|---|---|---|
| Backend projection | `--select id,name,current_nodes,work_item_status` | 命令声明支持后端 projection，需要减少后端返回字段 |
| Local output projection | `--output-select id,name,current_nodes,work_item_status` | 只想减少本地展示字段，不改变后端请求 |
| API-native fields | `--fields '["id","name"]'` | 底层 API 兼容参数，仅在命令特定场景或排障时使用 |

当前默认 projection-capable 工作项命令：

- `workitem get`
- `workitem search-by-params`

规则：

- 命令专属 flag 消歧先看 [cli-guide.md](cli-guide.md)：不要把 `--name`、`--work-item-type-key(s)`、`--work-item-id(s)`、`--select` / `--output-select` 在不同命令之间串用。
- `--select` 仅用于已确认 `projection.backend_select_supported == true` 的命令；上述普通读路径已有已验证 contract 时不固定 inspect，不确定/漂移时按 [cli-guide.md](cli-guide.md#命令发现) 检查。
- 在上述命令上，默认用 `--select` 表达产品化字段 projection；即使 live `inspect.parameters[]` 显示底层 `fields` 参数，也不要在普通展示路径改用 `--fields`。
- 不要同时传 `--select` 与 `--fields`。如果已经选择 `--select`，需要 `fields[]` 业务字段时直接把字段 key 放进同一个 `--select` 列表，例如 `--select id,name,work_item_status,current_status_operator`；但读取位置仍按“稳定顶层字段 allowlist / `fields[]` 业务字段”判断，`current_status_operator` 不会因此变成顶层字段。
- `workitem search-filter` 主要用于内置维度过滤；它不声明 backend projection，传 `--select` 会直接报错。如果只是想少展示字段，用 `--output-select`；若任务还关心总量或分布，默认直接读取返回里的 `pagination`。
- **`workitem search-filter` 的返回集合是固定内置字段，不包含 `fields[]` 业务字段**（live contract 无 `fields` 参数，传 `--output-select` 写业务字段也不会报错，只会静默缺失）。需要业务字段时走两段式：先用 `--output-select` 定位到 ID，再用 `workitem get --work-item-ids` 批量补取，不要指望 `search-filter` 直接返回。
- `workitem search-filter` 按名称搜索只接受 `--work-item-name`。不要把创建类命令的 `--name` 或其他系统的 `--keyword` 用在 `search-filter` 上，也不要先 probe 再自愈。
- 排障时先用 `--dry-run` 查看 `.params.data.fields` 是否出现，确认 projection 已进入后端请求。
- verified command 的 dry-run 如果因为未知顶层参数直接失败，优先检查 flag 名、`--params` 顶层 key，或重新用 `inspect --format json` 对照当前命令面。
- 当前后端在 `workitem get` / `workitem search-by-params` 上主要会收敛 `fields[]` 业务字段集合；稳定顶层字段 allowlist 中的字段仍可能按接口契约返回。不要把 `--select` 列表理解成 JSON 顶层路径列表。
- `--output-select` 对不存在的 key 是**静默丢弃**：既不报错也无声告警。需要确认字段真实存在时，先看同类型 `meta-fields`（业务字段）或 live `inspect`（参数面）。

### 批量读取与分页硬上限

以下上限由后端强制，写进命令前先按此设计，不要靠报错发现：

| 命令 | 上限 | 超限表现 | 正确做法 |
|---|---|---|---|
| `workitem get --work-item-ids` | **单次 50 个 ID** | `{"err_code":20028,"err_msg":"Workitem Ids Limit 50"}` | 本地按 50 切批，逐批 `workitem get` 后合并；不要传全量 ID 试一次 |
| `workitem search-filter --page-size` | **200** | `{"err_code":20006,"err_msg":"Invalid Param","err":{"msg":"page size should less than 200"}}` | 用 `--page-num` 分页，或按 bucket 拆查询 |

批量补取模板（当前展示页或当前任务集 ≤50 时一次完成）：

```bash
meegle workitem get \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-ids '[ID1,ID2]' \
  --fields '["current_status_operator"]' \
  --format json
```

当任务需要跨页总量或聚合分布，而你拿到的响应里**没有 `pagination`** 时，不要假定可以本地全量聚合：CLI 是 stateless 单次调用，无法在一条命令里跨页统计。此时要么明确告知不可行并给出替代路径（固定视图 / 图表），要么先确认该命令本来就不返回分页元信息。
---

## 关联字段过滤

**关联字段查询限制**：

- `search-by-params` 支持通过 `workitem_related_select` / `work_item_related_select` 和 `workitem_related_multi_select` / `work_item_related_multi_select` 类型字段进行正向查询（以 live `field_type_key` 为准，查询字段值包含指定工作项 ID 的工作项）
- **不支持** `work_item_related` 类型字段的搜索
- 反向关联查询优先从父工作项读取关联字段再批量查询；若目标类型有指向父工作项的可搜索关联字段，可用 `search-by-params` 直接查。


`workitem_related_select` / `work_item_related_select` 类型字段（如"所属项目"）在 `search-by-params` 中过滤时：

1. **value 是被关联工作项的数字 ID 数组**（`list<int64>`，不是字符串，也不是单个标量）
2. **ID 不是直接已知的**，需先查出来：先确定目标工作项类型，再按该类型的查询职责选命令
   - 基础名称匹配、内置维度过滤：用 `workitem search-filter`，名称条件必须用 `--work-item-name`，本地裁剪最多用 `--output-select id,name`
   - 字段级/复杂条件查询，或当前授权/接口契约不适合 `workitem search-filter`：用 `workitem search-by-params`
3. 字段 key 用 `workitem meta-fields` 查，按 `field_name` 定位，取 `field_key`

如果锚点类型已经由 `meta-types` 唯一确认（例如这里就是“迭代管理”），锚点 ID 查询必须直接限定在该 `type_key` 上。不要先裸跑 `workitem search-filter --work-item-name ...`，不要把全量 `type_key` 数组塞进 `search-filter` 做跨类型探测，也不要先用占位 type key 试探。

最终回复里如果说明关联字段查询，请明确写出：关联字段过滤的 `value` 使用被关联工作项的数字 ID 数组，不使用标题字符串。默认用 `operator: "HAS ANY OF"` 和 `value: [ID]`；即使在线文档列出 `=`，当前 CLI value shape 仍是数组，不要写成 `"operator":"=","value":20336086`。

```bash
# Step 1：如果目标类型支持基础名称匹配，用 search-filter 查目标 ID
meegle workitem search-filter \
  --project-key PROJ \
  --work-item-type-keys '["TARGET_TYPE_KEY"]' \
  --work-item-name "目标名称" \
  --output-select id,name \
  --page-size 10 \
  --format json
# 从返回 JSON 的 data[] 中读取 id 和 name。

# Step 1b：如果当前授权或接口契约不适合 search-filter，改用 search-by-params 查目标 ID
meegle workitem search-by-params \
  --project-key PROJ \
  --work-item-type-key TARGET_TYPE_KEY \
  --search-group '{"conjunction":"AND","search_params":[{"param_key":"people","operator":"HAS ANY OF","value":["USER_KEY"]}],"search_groups":[]}' \
  --format json
# 从返回 JSON 的 data[] 中读取 id 和 name。

# Step 2：查字段 key
meegle workitem meta-fields \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --output-select field_key,field_name,field_alias,field_type_key,options \
  --format json

# Step 3：用数字 ID 数组过滤
# search-by-params --search-group 中：
# {"param_key": "CUSTOM_FIELD_KEY", "operator": "HAS ANY OF", "value": [PROJECT_ID]}
#                                                                         ↑ 数字，不加引号
```

已唯一确认锚点 ID、关联字段 key 且普通条件 shape 已验证时直接执行最终查询；复杂新 shape、时间边界和排障的预览条件仍按 [cli-guide.md](cli-guide.md#命令发现) 保留。

如果锚点类型与字段 key 都已确定，推荐最终序列就是 4 步：

1. `meta-types`
2. 锚点 `search-filter`（限定锚点 type key）
3. 主体 `meta-fields`
4. 最终 `search-by-params`

不要加入 probe query、全类型探测或为格式化重复查询；必要发现、展示补取、分页及诊断不受该示例步数限制。

默认展示最终 `search-by-params` 应使用：

```bash
meegle workitem search-by-params \
  --project-key PROJ \
  --work-item-type-key SUBJECT_TYPE_KEY \
  --search-group '{"conjunction":"AND","search_params":[{"param_key":"RELATED_FIELD_KEY","operator":"HAS ANY OF","value":[ANCHOR_ID]}],"search_groups":[]}' \
  --select id,name,work_item_status,current_status_operator,created_at \
  --page-size 10 \
  --format json
```

不要把这里的 `--select` 改成 `--fields`；不要把 `[ANCHOR_ID]` 改成标量 `ANCHOR_ID`。

---

## 上下文推断

当命令需要业务线、所属项目或产品型号/子平台但用户未指定时，按以下顺序推断：

1. 若需要展示或回填业务线名称，可参考 `meegle auth whoami --format json` 的 `business_line_names`，但它只表示业务线只读 fallback 上下文，不代表普通工作项通用可见范围；若需要业务线 ID，用 `meegle space business-lines --project-key PROJ --format json` 按 `name` 匹配取 `id`
2. `workitem meta-types --project-key <project_key>` 找 `api_name == pdm` 的条目，取其 `type_key`；若只需要当前授权摘要，优先看 `meegle auth whoami --format json`。若需要项目明细，适用 [当前用户相关查询](#当前用户相关查询)：当前用户参与/相关的项目，`workitem search-filter` 必须显式加 `--user-keys '["<meegle_user_key>"]'`；只有在要看空间内全量项目管理工作项时，才允许不带 `--user-keys`；若需要更严格的字段级人员语义或当前授权/接口契约不适合 `search-filter`，再改用 `workitem search-by-params`
3. 同上找 `api_name == product_type` 的 `type_key`；再用 `workitem search-filter --work-item-type-keys '[<type_key>]'` 取产品型号/子平台，结果按业务线客户端过滤

每步规则：
- 单个结果 → 直接使用，不询问
- 多个结果 → 编号列表呈现，等待用户选择；业务线多个时先选业务线，再用业务线 ID 过滤后续查询

推断结果仅在当前任务相同适用上下文内复用，变化时按 [发现与复用](#发现与复用) 重新确认；不缓存权限。只有用户明确要求保存偏好，或当前环境明确提供可用 memory 工具时，才考虑持久化，避免无谓打断。

## workitem meta-types

列出空间下所有工作项类型。用户描述模糊时用此命令确认合法 `type_key`。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `--project-key` | string | 是 | 空间 `project_key` |

```bash
meegle workitem meta-types --project-key PROJ --format json
```

返回：`type_key`（UUID）、`name`（中英显示名）、`api_name`（如 `story_new`）。**写命令必须用 `type_key` UUID，不要用 api_name。**

类型解析规则：

- 显式指定优先精确匹配：`type_key`、精确 `api_name`、精确 `name` 只做精确命中，不做模糊扩展
- 模糊描述只在启用候选里解析：默认先过滤停用类型（`is_disable != 1`）
- 模糊描述只有唯一候选时才自动绑定；0 个候选时说明无法判定；多个候选时追问用户
- 禁止用 `.[0]`、首条近似项或通用 `api_name` 作为默认兜底
- 创建、列表、查询等面向“当前可操作类型”的任务默认按上述启用候选解析；URL 详情、历史对象读取等已知对象读取场景，若上下文已经唯一给出类型，可按该对象真实类型继续，不因停用状态而强行改绑到别的类型

---

## workitem meta-create-fields

获取指定工作项类型的创建元数据候选：字段名 / 字段类型 / 枚举可选值 / 模板等。`workitem create` 缺模板报错时也用它查 `template` 字段。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `--project-key` | string | 是 | 空间 `project_key` |
| `--work-item-type-key` | string | 是 | 工作项类型 UUID（来自 `workitem meta-types`） |

```bash
meegle workitem meta-create-fields \
  --project-key PROJ \
  --work-item-type-key 678de79dc62484dbfcc76150 \
  --format json
```

返回结构（节选）：

- `.data[]` —— 扁平字段数组；每个元素包含 `field_key` / `field_name` / `field_type_key` / `is_required` / `is_visibility` / `options[]`
- 模板不是顶层 `templates[]`，而是字段数组中 `field_key == "template"` 的那一项；其 `options[]` 就是可选模板

⚠️ 重要边界：

- `meta-create-fields` 是创建页元数据，主要用于字段发现、字段类型、模板和枚举查询
- 有效必填字段优先来自 `workitem create-preflight` 的 `missing_required_fields[]` / `required_fields[]`
- 旧 CLI / no-preflight 路径中，`is_required == 1 && is_visibility == 1` 只表示 CLI 本地可见必填保护范围
- `is_required == 1` 但 `is_visibility != 1` 的隐藏/条件可见字段不由 CLI 前置阻断，交给后端 create 做最终校验
- 如果某个可见必填字段在 `workitem create` 中返回 `field [xxx] is illegal`，这是元数据与 create API 的契约不一致
- 不要删除可见必填字段绕过创建；应停止并报告该契约问题

字段写入格式见 `sop-create-workitem.md` / `sop-update-workitem.md`。具体命令参数仍以 `meegle inspect workitem.create --format json` 和 `meegle inspect workitem.update --format json` 为准。

---

## workitem create-preflight

写入前只读评估当前创建 payload 的有效必填字段，不会创建或修改工作项。优先用它指导用户补齐字段，再调用 `workitem create`。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `--project-key` | string | 是 | 空间 `project_key` |
| `--work-item-type-key` | string | 是 | 工作项类型 UUID（来自 `workitem meta-types`） |
| `--name` | string | 是 | 准备创建的标题 |
| `--template-id` | string | 否 | 准备使用的模板 ID |
| `--field-value-pairs` | JSON array | 否 | 已准备写入的字段值 |

关键返回字段：

- `required_fields[]`：当前上下文有效必填字段
- `missing_required_fields[]`：payload 尚未提供的有效必填字段
- `conditional_required_fields[]`：meta 标记必填但当前未被 preflight 强制的隐藏/条件字段
- `provided_fields[]`：payload 已满足的字段
- `source`：`backend_effective_meta` / `mcp_visibility_fallback` / `backend_create_error`
- `confidence`：`high` / `medium` / `low`

当 `source == "mcp_visibility_fallback"` 且 `confidence == "medium"` 时，这是降级判断；仍可据此补齐明显缺失字段，但最终以后端 `workitem create` 结果为准。不要为输入法、穿戴设备、发布版本等产线字段维护硬编码豁免名单。

`workitem create-preflight` 只用于必填缺失判断，不是 `field_value_pairs` 白名单。用户明确提供的非必填字段应按字段类型转换后继续传给 `workitem create`；若该字段不被后端接受，应返回或处理 create 错误，而不是在 preflight 后静默丢弃。

---

## 常见用法

```bash
# 1. 不知道空间用啥类型 — 列出来
meegle workitem meta-types --project-key PROJ --format json

# 2. 拿到 type_key 后，看字段定义
meegle workitem meta-create-fields \
  --project-key PROJ \
  --work-item-type-key 678de79dc62484dbfcc76150 \
  --output-select field_key,field_name,field_type_key,is_required,is_visibility \
  --format json

# 3. 找枚举字段的合法 option
meegle workitem meta-create-fields \
  --project-key PROJ \
  --work-item-type-key 678de79dc62484dbfcc76150 \
  --output-select field_key,field_name,field_type_key,options \
  --format json
```

从第 3 条返回 JSON 中找到 `field_key == "priority"` 的字段，再读取它的 `options[]`。

---

## 富文本与描述图片（workitem get 默认返回 images）

`fields[]` 里的 `multi_text` 字段默认只给纯文本，描述中的图片显示为 `[图片]` 占位。`workitem get` **不需要任何 expand 参数**，返回的工作项对象自带顶层 `images` 摘要（服务端已默认取回富文本并裁剪为图片清单，不返回 doc/doc_html 大段原始富文本）：

```json
{
  "id": 20655077,
  "fields": [ /* description.field_value 仍是纯文本字符串 */ ],
  "images": [
    { "field_key": "description",
      "images": [ { "uuid": "0814BD6E-81DA-4333-A6CC-5B9170DD2E8F" } ] }
  ]
}
```

取图流程（两步，均为现有命令）：

```bash
# 1. get 默认返回已含 images（无需 --expand）
meegle workitem get --work-item-ids '[20655077]' --work-item-type-key 67c7c0e46f6789d587d7ab5e

# 2. 用 images[].uuid 下载原图
meegle attachment download --work-item-id 20655077 \
  --work-item-type-key 67c7c0e46f6789d587d7ab5e \
  --uuid 0814BD6E-81DA-4333-A6CC-5B9170DD2E8F --output screenshot.png
```

要点：

- `uuid` 是下载主键；`src`（如出现在任何 raw 输出里）是网页展示 URL，需浏览器登录会话，程序化取图一律走 `uuid`。
- 只有真正嵌图的多文本字段会出现在 `images` 里；无图工作项该数组为空。
- **不要**为了看图给 `workitem get` 传 `--expand '{"need_multi_text":true}'`——那会返回 raw doc/doc_html 大 payload，默认已不需要。仅当你确实要原始富文本结构时才显式传该参数。

### 分层默认：元数据人人可见，图片按任务类下载

- **协议层（`workitem get` 返回）**：默认只带 uuid 清单（`images`），不带图片二进制——所有读取场景零额外流量。
- **编排层（Agent 执行默认）**：
  - **分析 / 修复 / 评审类任务**（读缺陷/需求详情需结合截图分析问题）：`workitem get` 返回的 `images` 非空时，**默认把该工作项的图片全部下载到本地**再分析：
    ```bash
    # 每个 images[].images[].uuid 一条；多图可并行发起（同一工作项的下载互不依赖）
    meegle attachment download --work-item-id <id> \
      --work-item-type-key <type_key> --uuid <uuid> --output desc-<n>.png
    ```
    下载完成后先读图（本地文件），再结合描述文字给出结论；不要把“图片占位 `[图片]`”当结论。
  - **只读 / 列表 / 字段核对类任务**：不下载，回答时注明「描述含 N 张截图（uuid 可下载）」即可。
- 图片下载走 plugin 鉴权，无需浏览器会话；产物为本地原图文件。

### 生效前提与降级

- 该能力依赖 meegle-mcp 新版（`workitem get` 默认返回 `images`）。若实际返回**没有** `images`（旧 server / 未发布），需要看图时只能用兜底路径：显式 `--expand '{"need_multi_text":true}'` 拉取富文本后从 `multi_texts[].field_value.doc` 的 image ops 中解析 `uuid`（payload 较大，仅兜底用），再 `attachment download`。
