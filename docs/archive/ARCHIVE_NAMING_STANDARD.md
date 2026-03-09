# ARCHIVE_NAMING_STANDARD（归档命名与元信息规范）

## 1. 适用范围
- 适用于 `docs/archive/` 下新增归档文档。
- 历史遗留文件可保留原名，但必须在 `ARCHIVE_CATALOG.md` 建立标准化映射。

## 2. 标准命名格式
- 文件名：`ARC-<TYPE>-<YYYYMMDD>-<slug>.md`
- 说明：
  - `TYPE`：`INC|RET|REL|ADR|OPS|LEG|CHG`
  - `YYYYMMDD`：归档日期（北京时间）
  - `slug`：小写短语，使用 `-` 分隔

示例：
- `ARC-INC-20260309-30m-diagnosis.md`
- `ARC-REL-20260309-v4-2-9-hotfix.md`
- `ARC-CHG-20260309-req-watchlist-sort.md`

## 3. Archive-Meta 信息块（建议写入正文顶部）
```md
> Archive-Meta
- Archive-ID: ARC-INC-20260309-30m-diagnosis
- Archive-Type: INC
- Archived-At: 2026-03-09
- Source-Path: docs/changes/INV-20260309-03-30m-gap-check.md
- Status: FROZEN
```

## 4. 存放目录约定
- 事件类：`docs/archive/incidents/`
- 变更卡：`docs/archive/changes/`
- 其他历史：`docs/archive/`（并在 catalog 标注类型）

## 5. 兼容策略
- 历史文件不强制批量重命名；
- 但新增归档必须使用本规范；
- 历史文件需在 `ARCHIVE_CATALOG.md` 记录“当前名 -> 标准名”。
