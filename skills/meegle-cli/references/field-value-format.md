# 字段值入参规范（field_value format）

> **Source**: <https://project.feishu.cn/b/helpcenter/2.0.0/1p8d7djs/1tj6ggll>（飞书项目「字段与属性解析格式」官方文档，2026-05 抓取）。
> 本文按 `field_type_key` 索引，给出 `field_value_pairs` / `update_fields` 写入时每个类型的**入参 shape + 完整条目示例 + 错误样式 + value 来源**。
>
> **🚨 强制约束**：
> 1. 构造 `workitem create` / `workitem update` / `workflow transition --fields` / `workflow transition-state --fields` / `workflow update-node --fields` 的 `field_value` 前，**必须先查本文档**找到对应 `field_type_key` 的 shape。
> 2. 本文是唯一字段格式索引，不代表当前所有入口/字段均可写。下表来自官方文档及历史记录；执行仍须核对当前目标元数据与 public descriptor，不能由 generic array/object schema 推断内层全部字段兼容。
> 3. **禁止凭经验、记忆或别处规则推断 shape**——尤其禁止把数组/对象 `JSON.stringify` 再传字符串。历史记录中部分字段的该写法被 `field [...] is illegal` 拒绝（见文末偏差留痕）。
> 4. 不确定字段类型时先调 `meegle workitem meta-create-fields --project-key PROJ --work-item-type-key TYPE --format json` 看 `field_type_key`。
> 5. 不确定 select / radio 等枚举的合法 `value` 时也走同一个接口，从 `options[].value` 取真实 option_id（不是文档里示例的 `"0"`、`"1"`，那只是占位）。

---

## 速查总表

| field_type_key | 入参 shape | 一句话 |
|---|---|---|
| `text` | string | 单行/多行文本 |
| `multi_text` | string 或 富文本结构体数组 | 富文本字段；简单文本可直接传 string |
| `select` | `{label?, value}` | 单选；priority 等系统字段也走这条 |
| `multi_select` | `[{label?, value}, ...]` | 多选 |
| `radio` | `{label?, value}` | 单选按钮 |
| `tree_select` | `{value, label?, children}` 嵌套 | 级联单选 |
| `tree_multi_select` | `[{value, label?, children}, ...]` | 级联多选 |
| `user` | string (user_key) | 单选人员 |
| `multi_user` | string[] (user_key 数组) | 多选人员；**不是** stringified 数组 |
| `date` | number (毫秒戳, 64 位) | 日期 / 日期时间共用此类型 |
| `schedule` | `{start_time, end_time}` 毫秒戳对 | 日期区间 |
| `number` | float | 数字 |
| `bool` | bool | 开关 |
| `signal` | 可空 bool | 系统外信号 |
| `link` | string (URL) | URL 链接 |
| `link_cloud_doc` | string[] (URL 数组) | 飞书云文档 |
| `business` | string (业务线 ID) | 业务线 |
| `group_type` | enum string: `auto` / `disabled` / `bind` | 拉群方式 |
| `work_item_related_select` | **number** (实例 ID, 64 位) | 单选关联工作项 |
| `work_item_related_multi_select` | **number[]** (实例 ID 数组) | 多选关联工作项 |
| `compound_field` | 二维结构体数组 | 复合字段，复杂 |
| `role_owners` | `[{role, owners[]}, ...]` | 角色与人员 |
| `email` / `telephone` | string + 正则 | 邮箱 / 电话 |
| `multi_file` | ❌ 不能直接写 `field_value` | 走 `attachment upload` 接口 |
| `multi_signal` | ❌ 已废弃 | — |
| `aborted` / `deleted` / `template` / `start_time` / `finish_time` 等系统字段 | ❌ 不支持自定义入参 | 由系统计算 |
| 计算字段（公式）| ❌ 只读 | — |

---

## 自定义字段

### text（单行/多行文本）

- **入参类型**：`string`
- **出参类型**：`string`

```json
{
  "field_key": "field_a2697f",
  "field_type_key": "text",
  "field_alias": "",
  "field_value": "单行文本"
}
```

多行：`"field_value": "多行文本\n多行文本\n多行文本"`

### multi_text（富文本）

- **简单入参**：`string`（仅纯文本时）
- **完整入参**：结构体数组（详见富文本 reference）
- **出参（`workitem get` 默认）**：`fields[].field_value` 为 `string`（纯文本，描述中图片显示为 `[图片]` 占位）；**同时工作项顶层带 `images` 数组**：`[{ field_key, images: [{ uuid }] }]`，uuid 是嵌图的多文本字段里图片的下载主键（配 `attachment download` 取原图）
- **出参（仅显式 `--expand '{"need_multi_text":true}'` 时）**：raw 富文本结构 `{doc, doc_text, doc_html, is_empty}` 随 `multi_texts` 返回（不裁剪，payload 较大）

默认取图不传 expand：`workitem get` 返回即带 `images`。raw doc/doc_html 只在确实需要原始富文本时才用显式 expand 获取。

简单示例：
```json
{
  "field_key": "description",
  "field_type_key": "multi_text",
  "field_value": "一段说明"
}
```

富文本结构示例：
```json
{
  "field_key": "field_1e9078",
  "field_type_key": "multi_text",
  "field_alias": "",
  "field_value": [
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "文本",
          "attrs": { "fontColor": "blue", "italic": "true", "underline": "true" }
        }
      ]
    }
  ]
}
```

完整富文本传参语法（type 枚举、attrs、颜色列表等）见
[rich-text-editor-markdown-syntax.md](rich-text-editor-markdown-syntax.md)。

### select（单选 / 含 priority 等系统字段）

- **入参类型**：结构体 `{label?, value}`，`value` 是 option_id（**必填**），`label` 入参时可选
- **出参类型**：同结构体

✅ 正确示例：
```json
{
  "field_key": "field_312244",
  "field_type_key": "select",
  "field_alias": "",
  "field_value": { "label": "选项1", "value": "8lheuaepp" }
}
```

priority（系统内置 select，`field_alias=priority`）：
```json
{
  "field_key": "priority",
  "field_type_key": "select",
  "field_alias": "priority",
  "field_value": { "label": "P0", "value": "0" }
}
```
> ⚠️ 文档示例中 priority 的 `value: "0"` 是**示例占位**。**不同租户的 priority option_id 各不相同**，必须从 `meegle workitem meta-create-fields` 返回的 `priority.options[].value` 取实际值（比如本仓库私有空间 `cbg_product_develop` 是 `option_1..option_3 / ythrqjjlw`，不是 `0..3`）。

❌ 常见错误：
- `"field_value": "8lheuaepp"` ← 后端报 `field [...] is illegal`（实际意思是 shape 错）
- `"field_value": "{\"value\":\"8lheuaepp\"}"` ← stringified 也算 shape 错
- `"field_value": { "value": "0" }` ← 文档示例的 `"0"` 不是字面值

**value 来源**：`meegle workitem meta-create-fields --project-key PROJ --work-item-type-key TYPE`，找该字段的 `options[].value`。

### multi_select（多选）

- **入参类型**：结构体数组
- **出参类型**：结构体数组

```json
{
  "field_key": "field_c4d17a",
  "field_type_key": "multi_select",
  "field_alias": "",
  "field_value": [
    { "label": "选项1", "value": "b0gzgge5o" },
    { "label": "选项4", "value": "et15_j7yl" }
  ]
}
```

### radio（单选按钮）

shape 与 `select` 完全一致：

```json
{
  "field_key": "field_0dae57",
  "field_type_key": "radio",
  "field_alias": "",
  "field_value": { "label": "选项1", "value": "zgw2edjby" }
}
```

### tree_select（级联单选）

- **入参/出参**：结构体（嵌套 `children`）

```json
{
  "field_key": "field_511b0c",
  "field_type_key": "tree_select",
  "field_alias": "",
  "field_value": {
    "value": "drvmnhhb0",
    "label": "选项1",
    "children": {
      "value": "xcmczov_k",
      "label": "子选项2",
      "children": null
    }
  }
}
```

### tree_multi_select（级联多选）

- **入参/出参**：结构体数组

```json
{
  "field_key": "field_38c836",
  "field_type_key": "tree_multi_select",
  "field_alias": "",
  "field_value": [
    {
      "value": "ejhouugxx",
      "label": "选项1",
      "children": {
        "value": "2jks8ykdf",
        "label": "子选项2",
        "children": null
      }
    },
    {
      "value": "ejhouugxx",
      "label": "选项1",
      "children": {
        "value": "cao254c6n",
        "label": "子选项3",
        "children": null
      }
    }
  ]
}
```

### user（单选人员）

- **入参类型**：`string`（user_key）
- **出参类型**：`string`

```json
{
  "field_key": "field_05723d",
  "field_type_key": "user",
  "field_alias": "",
  "field_value": "735679528XXXXX"
}
```

### multi_user（多选人员）

- **入参类型**：`string[]`（user_key 数组）
- **出参类型**：`string[]`

```json
{
  "field_key": "field_8b18fd",
  "field_type_key": "multi_user",
  "field_alias": "",
  "field_value": ["735679528XXXXX", "731189198XXXXX"]
}
```

> ⚠️ **不要 stringify**。历史 skill 文档中"multi_user 必须 stringified `\"[\\\"k1\\\",\\\"k2\\\"]\"`"的说法**与官方文档不符**，按本规范以原生数组传入。

### date（日期 / 日期时间）

- **入参类型**：`number` (毫秒时间戳, 64 位)
- **出参类型**：`number`

天精度（日期）：
```json
{
  "field_key": "field_2fbca6",
  "field_type_key": "date",
  "field_alias": "",
  "field_value": 1722182400000
}
```
> 建议传 `00:00:00` 的当天起始毫秒戳。

秒精度（日期时间）：
```json
{
  "field_key": "field_0e381c",
  "field_type_key": "date",
  "field_alias": "",
  "field_value": 1722220183000
}
```

### schedule（日期区间）

- **入参/出参**：`{start_time, end_time}` 毫秒戳对

```json
{
  "field_key": "field_3d786b",
  "field_type_key": "schedule",
  "field_alias": "",
  "field_value": {
    "start_time": 1722182400000,
    "end_time":   1722355199999
  }
}
```
> 约定：`start_time` 用 `00:00:00`，`end_time` 用 `23:59:59`。

### number（数字）

- **入参/出参**：`float`

```json
{
  "field_key": "field_3724e6",
  "field_type_key": "number",
  "field_alias": "",
  "field_value": 11.11111111111111
}
```

### bool（开关）

- **入参/出参**：`bool`

```json
{
  "field_key": "field_b9d821",
  "field_type_key": "bool",
  "field_alias": "",
  "field_value": false
}
```

### signal（系统外信号）

- **入参/出参**：可空 bool。`true` = 已通过，`false` = 未通过，`null` = 处理中

```json
{
  "field_key": "field_1c7e08",
  "field_type_key": "signal",
  "field_alias": "",
  "field_value": null
}
```

### link（URL 链接）

- **入参/出参**：`string`

```json
{
  "field_key": "field_ec6e0b",
  "field_type_key": "link",
  "field_alias": "",
  "field_value": "https://project.feishu.cn/home"
}
```

### link_cloud_doc（飞书云文档）

- **入参/出参**：URL **数组**

```json
{
  "field_key": "field_347e4e",
  "field_type_key": "link_cloud_doc",
  "field_alias": "",
  "field_value": ["https://ydrp2xxxxm.feishu.cn.com/wiki/CxiuwrvbXXXXXXk8idacjXj3nfc"]
}
```

### work_item_related_select（单选关联工作项）

- **入参类型**：`number`（关联实例 ID，64 位）
- **出参类型**：`number`

```json
{
  "field_key": "field_7872c9",
  "field_type_key": "work_item_related_select",
  "field_alias": "",
  "field_value": 4812084224
}
```

> 名称 → ID 转换（搜索、消歧与循环引用保护）见 [field-value-extras.md](field-value-extras.md)，字段 shape 只在本文维护。

### work_item_related_multi_select（多选关联工作项）

- **入参/出参**：`number[]`

```json
{
  "field_key": "field_971f4e",
  "field_type_key": "work_item_related_multi_select",
  "field_alias": "",
  "field_value": [4831452515, 4812084224]
}
```

### compound_field（复合字段）

- **入参/出参**：二维结构体数组（外层 = 多行数据，内层 = 多类型子字段）

```json
{
  "field_key": "field_5a711c",
  "field_type_key": "compound_field",
  "field_alias": "",
  "field_value": [
    [
      { "field_key": "field_fdd359", "field_type_key": "text", "field_value": "子字段1内容" },
      { "field_key": "field_284451", "field_type_key": "date", "field_value": 1722355200000 }
    ],
    [
      { "field_key": "field_fdd359", "field_type_key": "text", "field_value": "子字段2内容" },
      { "field_key": "field_284451", "field_type_key": "date", "field_value": 1722355200000 }
    ]
  ]
}
```

> 实战中复合字段 API 写入容易触发后端校验意外，**优先建议页面手动维护**。

### email（电子邮件）

- **入参/出参**：`string`
- 正则约束：`^[^@\r\n]+@[^@\r\n]+$`，不超过 254 字符

```json
{
  "field_key": "field_a2697f",
  "field_type_key": "email",
  "field_alias": "",
  "field_value": "test@gmail.com"
}
```

### telephone（电话号码）

- **入参/出参**：`string`
- 正则约束：`(?:\+?[0-9]{1,4})?(?:[-()\*#]*[0-9]){3,50}`，不超过 54 字符

```json
{
  "field_key": "field_a2697f",
  "field_type_key": "telephone",
  "field_alias": "",
  "field_value": "10086"
}
```

---

## 系统内置字段

### business（业务线）

- **入参/出参**：`string`（业务线 ID）

```json
{
  "field_key": "business",
  "field_type_key": "business",
  "field_alias": "business",
  "field_value": "662f0e13b1a20d5dd5fb3320"
}
```
业务线 ID 通过 `meegle space business-lines --project-key PROJ` 获取。

### role_owners（角色与人员）

- **入参/出参**：结构体数组

```json
{
  "field_key": "role_owners",
  "field_type_key": "role_owners",
  "field_alias": "",
  "field_value": [
    { "role": "Data",      "owners": ["7311891981507100700"] },
    { "role": "Server",    "owners": ["7311891981507100700"] },
    { "role": "UX_Writer", "owners": ["7311891981507100700", "7374823452487794692"] },
    { "role": "role_bb4853", "owners": null }
  ]
}
```

### group_type（拉群方式）

- **入参/出参**：字符串枚举：`auto` / `disabled` / `bind`

```json
{
  "field_key": "group_type",
  "field_type_key": "group_type",
  "field_alias": "",
  "field_value": "disabled"
}
```

### watchers（关注人）

- **入参/出参**：`string[]`（user_key 数组）；底层 `field_type_key=multi_user`

```json
{
  "field_key": "watchers",
  "field_type_key": "multi_user",
  "field_alias": "watchers",
  "field_value": ["735679528040XXXXXX"]
}
```

---

## 不支持 API 写入的字段类型

以下字段不能作为通用字段默认写入；先说明限制并确认用户授权，再走已公开专用接口或页面，不能自动换路径：

| 字段类型 | 处理方式 |
|---|---|
| `multi_file`（附件） | 走 `attachment upload` 接口（[attachment.md](attachment.md)） |
| `vote-boolean` / `vote-option` / `vote-option-multi` | 仅支持页面交互 |
| 计算字段 / 公式（出参 type 为 `number`/`bool`/`string` 但 alias 是公式字段）| 只读 |
| `aborted` | 走 `workitem abort` / `workitem restore` |
| `deleted` | 当前 public CLI 不暴露删除工作项命令；如需删除，只能走页面或经单独评审的内部流程 |
| `start_time` / `finish_time` / `created_at` / `updated_at` / `deleted_at` / `archiving_date` / `archiving_status` | 系统计算 |
| `current_status_operator` | 系统计算 |
| `template` / `template_id` / `template_type` | 用 `workitem create` 的 `--template-id` 顶层参数 |
| `id` / `project_key` / `work_item_type_key` / `pattern` / `current_nodes` | 系统/路径参数，非 field |
| `multi_signal`（已废弃） | — |
| `chat_group` / `group_id` | 系统维护 |

---

## 偏差留痕：与 upstream / 历史 stringify 规则的关系

### upstream `larksuite/meegle-cli` 的 STRING 协议

upstream 公开版 SKILL.md 写过：

> `field_value` 协议层固定为字符串。数组、对象必须先 JSON.stringify 再传。

**该规则不适用于本私有 fork**。upstream 的 STRING 协议针对它自己的中间层 CLI（flag → JSON 转换层），而本仓库走 stdio MCP 透传后端 OpenAPI，契约直接对齐飞书项目官方 OpenAPI（即本文上半部分各表格的原生 shape）。

私有后端实测（2026-05-18，`cbg_product_develop` 空间，通过 MCP 直调 `workitem.create` 和 `workitem.update`）：

| 测试形态 | create | update |
|---|---|---|
| `select` 传 `"option_3"` 字符串 | ❌ `field [priority] is illegal` | ❌ illegal |
| `select` 传 stringified `"{\"label\":..,\"value\":..}"` | ❌ illegal | ❌ illegal |
| **`select` 传原生 `{label, value}` 对象** | **✅** | **✅** |
| `multi_select` 传 `"[{\"option_id\":..}]"` stringified | ❌ illegal | ❌ illegal |
| **`multi_select` 传原生 `[{label,value}]` 数组** | **✅** | **✅** |
| `date` 传 `"1780156800000"` 字符串 | ❌ illegal | ❌ illegal |
| **`date` 传原生数字** | **✅** | **✅** |

以上是 2026-05-18 的历史记录，未在本轮重新业务写入验证，不证明当前所有类型、workflow 入口或租户契约对称。2026-09-09 只读 public inspect 返回 create/update 字段列表为 array<object>，没有内层字段 schema；当前字段级可写性仍需目标元数据/授权测试确认。

### 历史 skill 文档的 stringify 指引

本仓库历史的 [sop-update-workitem.md](sop-update-workitem.md) / [error-handling.md](error-handling.md) 也曾沿用 upstream STRING 协议描述。**以本文为准**：所有结构化字段以原生 JSON 对象/数组传入。

后端报错 `field [xxx] is illegal` 的真实含义往往是 **shape 不匹配**（如把 select 字段传成字符串），而非"字段被禁止写入"——别再被这条错误信息误导成"plugin 字段白名单封锁"或"meta/create 契约不一致"。

---

## 字段写入排错速查

| 后端报错片段 | 真实原因 | 修复 |
|---|---|---|
| `field [X] is illegal` | 可能是 shape、选项、权限或目标契约问题 | 核对目标类型与错误，保持用户字段，不猜测兼容格式 |
| `Field Option Value Is Wrong` (err_code 20050) | shape 对了，但 option_id 用错（比如照搬文档示例 `"0"`）| 调 `meta-create-fields` 取真实 `options[].value` |
| `当前选项值已失效` | 关联字段绑定的目标实例被管理员标失效 | 用 `search-by-params` 查目标类型当前生效实例，换 ID |
| `Required Field Is Not Set` | meta `is_required=1` 字段缺值 | 补齐必填字段；优先级、模板等都属 meta 必填 |
| `field [X]` 在 create / update 表现不同 | 当前目标契约待确认 | 停止无依据的类型切换，披露无法确认项 |
