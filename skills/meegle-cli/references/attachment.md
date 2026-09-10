# 附件域

当前私有 CLI 的附件域以 **MCP 实际工具** 为准，不沿用 upstream 的两段式 `prepare-*` / `+upload` / `+download` 协议抽象。

可公开使用的 attachment 命令：

- `attachment upload-file`
- `attachment upload`
- `attachment download`
- `attachment delete`

附件命令不是默认高频路径。执行前先运行：

```bash
meegle inspect attachment.upload-file --format json
meegle inspect attachment.upload --format json
meegle inspect attachment.download --format json
meegle inspect attachment.delete --format json
```

确认参数形态后再执行。不要复用 upstream 的 `prepare-*` 或 `+upload` / `+download` 示例。

`--file` 始终填写当前 CLI 客户端可读取的本机文件路径。安装版 CLI 会在本机读取该文件，并把文件内容发送给共用远端 MCP Server；普通用户和 Agent 不需要启动本地 MCP Server，也不要手工传 base64 或服务端本地路径。

上传前可用 `--dry-run --format json` 预览 normalized request。附件上传的 dry-run 只展示本机路径、文件名、大小、内容类型和传输方式，不输出文件内容或 base64 数据。新版 MCP Server 发布 `file_upload.transport=http_multipart` capability 后，CLI 会以 multipart 文件流上传，不再把文件编码为 JSON/base64。

如果服务端没有发布 multipart capability，CLI 会保留旧的 MCP JSON tool 兼容路径；大文件仍可能受到 JSON body 限制。遇到 413 时，应升级 MCP Server 与 CLI，使 `attachment.upload` manifest 含有 `file_upload.transport = "http_multipart"`。

---

## attachment upload-file

上传文件到项目空间，适合富文本图片、通用文件等不直接绑定工作项附件字段的场景。

```bash
meegle attachment upload-file \
  --project-key PROJ \
  --fileName image.png \
  --file /absolute/path/image.png \
  --format json
```

dry-run 示例：

```bash
meegle attachment upload-file \
  --project-key PROJ \
  --fileName image.png \
  --file /absolute/path/image.png \
  --dry-run \
  --format json
```

## attachment upload

上传附件到已有工作项字段。当前私有 CLI 需要绑定工作项上下文，并且必须用 `--field-key` 或 `--field-alias` 指明附件字段；两者恰好传一个，推荐使用 `--field-key`。

字段 key 只能来自当前空间 / 工作项类型的字段元数据，不要把历史 case 里的 `field_*` 复用到其它空间或类型。上传前先定位 `field_type_key == "multi_file"` 的字段：

```bash
meegle workitem meta-fields \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --output-select field_key,field_name,field_alias,field_type_key \
  --format json
```

从返回的 `data[]` 中选择 `field_type_key == "multi_file"` 的字段，优先把它的 `field_key` 传给 `attachment upload`。如果没有唯一附件字段，不要猜，先让用户确认要挂到哪个附件字段。

```bash
meegle attachment upload \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-id 12345 \
  --field-key field_xxx \
  --fileName a.pdf \
  --file /absolute/path/a.pdf \
  --format json
```

dry-run 示例：

```bash
meegle attachment upload \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-id 12345 \
  --field-key field_xxx \
  --fileName a.pdf \
  --file /absolute/path/a.pdf \
  --dry-run \
  --format json
```

如果缺少 `--field-key` 和 `--field-alias`，CLI 会直接返回 `FIELD_KEY_OR_ALIAS_REQUIRED`，不会发起远端上传。此时回到上面的 `workitem meta-fields` 步骤定位 `multi_file` 字段。不要同时传 `--field-key` 和 `--field-alias`；同时传入会返回 `FIELD_KEY_AND_ALIAS_CONFLICT`。

返回中的 `file_token` / 文件元数据用于后续字段写入。附件字段通常是覆盖语义；追加附件时先读取旧值，合并后再写回。

## attachment download

按附件 UUID 下载已有工作项附件。`uuid` 必须来自接口返回，不要从页面 URL 手工拼接。CLI 通过当前 MCP Server 发布的鉴权 HTTP stream 直接写入本地文件，不会把附件字节转成 UTF-8 或 JSON 字符串。

```bash
meegle attachment download \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-id 12345 \
  --uuid ATTACHMENT_UUID \
  --output-dir ./downloads \
  --format json
```

- `--output /path/to/file`：使用指定的完整文件路径。
- `--output-dir /path/to/dir`：使用服务端返回的附件文件名写入指定目录。
- 两者都不传：写入当前目录。
- 默认不覆盖已有文件；确需替换时显式传 `--force`。
- CLI 先写同目录临时文件，校验 `Content-Length` 后再原子发布；下载中断不会留下目标半文件。

成功时 stdout 只返回 `path`、`filename`、`content_type`、`size_bytes` 元数据。例如：

```json
{
  "path": "/absolute/path/downloads/sample.jpg",
  "filename": "sample.jpg",
  "content_type": "image/jpeg",
  "size_bytes": 123456
}
```

不要使用 `--format json > attachment.jpg` 获取附件内容；`--format` 只控制上述元数据的展示格式。如果服务端未发布无损下载 capability，CLI 会返回 `ATTACHMENT_BINARY_DOWNLOAD_UNSUPPORTED`，此时升级远端 Meegle MCP Server 并加 `--refresh` 重试，不会回退到旧的文本 MCP 响应。

### 大小上限与超大附件降级

平台对单个附件的下载有 **100MB 上限**（上游返回 `File Size Limit 100M`）。超限时 CLI 返回 `ATTACHMENT_DOWNLOAD_TOO_LARGE`，错误信息保留上游原文，`retryable` 为 `false`——**不要重试，重试不会成功**。

其它非 2xx 失败同样会在错误信息里带上游响应体摘要（例如 `err_code` / `err_msg`）。先读这条信息再决定动作，不要把它当成无信息的泛化失败。

下载前先判断大小，避免无意义请求：

```bash
# 附件的 size 字段来自工作项附件字段，例如 "552.8MB"
meegle workitem get \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-ids '[WORK_ITEM_ID]' \
  --fields '["ATTACHMENT_FIELD_KEY"]' \
  --format json
```

超过上限时的可执行降级：

1. **要求更小的附件**：请附件上传方压缩、拆分，或只上传需要的关键片段。
2. **分段拉取**：仅当任务必须读取超大文件的局部内容时，用附件字段返回的 `url`（配合已登录的浏览器会话）做 HTTP Range 分段拉取，例如只取尾部若干 MB；**不要**尝试把整个文件读进会话。
3. **明确披露**：无法获取时直接告诉用户是超出平台上限，不要反复重试或声称已读取。

> Range 分段属于兜底手段，依赖浏览器登录态与上游存储接口，不是 CLI 能力；能用第 1 条解决时优先用第 1 条。

## attachment delete

按 UUID 从工作项附件中删除文件。**destructive 命令，必须带 `--confirm` 才能执行**；使用前应确认目标工作项、字段和待删 UUID 列表。

```bash
meegle attachment delete \
  --project-key PROJ \
  --work-item-id 12345 \
  --field-key field_xxx \
  --uuids '["uuid-a","uuid-b"]' \
  --confirm \
  --format json
```

上传/下载属于低频路径；`delete` 属于 destructive 命令，只在用户明确要求删除附件时使用，并提示删除不可恢复。
