# 字段值进阶：关联工作项名称 → ID 转换

当用户为 `workitem_related_select` / `workitem_related_multi_select` 字段提供的是**工作项名称而非 ID** 时，按以下流程转换后再写入。

1. **获取关联字段的目标约束**：从 `meegle workitem meta-create-fields` 返回的该字段配置中，提取其绑定的**目标空间**（`project_key`）和**目标工作项类型**（`work_item_type_key`）。若配置未限定（可关联任意类型），默认在当前空间内搜索。
2. **按名称搜索目标工作项**：优先调用 `meegle workitem search-filter`，在目标空间和类型范围内按名称匹配。
   ```bash
   meegle workitem search-filter \
     --project-key PROJ \
     --work-item-type-keys '["TYPE_KEY"]' \
     --work-item-name "用户给的名称" \
     --page-size 10 \
     --format json
   ```
   需要字段级条件时改用 `meegle workitem search-by-params`，参数形态先看 `meegle inspect workitem.search-by-params --format json`。
3. **消歧处理**：
   - 唯一结果 → 直接取工作项 ID
   - 多个结果 → 列出所有匹配项（ID + 名称 + 状态）让用户确认
   - 零结果 → 提示用户"未找到名为 XXX 的工作项，请确认名称或直接提供 ID"
4. **写入格式**：唯一来源见 [field-value-format.md](field-value-format.md)。关联单选用原生 number，多选用原生 number[]；外层 CLI 参数 JSON 编码不改变内层类型。无当前目标契约证据时停止并披露，不因类型报错盲目切换字符串重试。
5. **循环引用保护**：写入前必须排查当前工作项自身 ID，**禁止将自身 ID 写入关联字段**，否则会触发 `exists loop`（循环引用）报错。
