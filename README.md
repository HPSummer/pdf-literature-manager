# PDF 文献管理器

Windows 一键 PDF 文献管理工具，面向论文、硕士/博士学位论文和普通 PDF 的整理、引用、重命名与 Obsidian 知识库归档。

## 功能

- 自动扫描当前文件夹或指定文件夹中的 PDF
- 识别期刊/会议论文、硕士论文、博士论文、普通 PDF 和待复核文件
- 默认按 GB/T 7714 生成引用和安全文件名
- 支持 IEEE、APA、MLA、Chicago、GB/T 7714
- 生成 `references.bib`、`references.ris`、Markdown 引用列表和 CSV/JSON 索引
- 生成 Obsidian 文献笔记，并可一键复制到 vault 的 `02_literature`
- 支持 Obsidian 笔记模板和目标子目录配置，模板可使用 `zotero_key`、`citation_gbt`、`citation_ieee`、`school`、`place` 等变量
- 支持 Zotero 等文献管理软件导入 BibTeX/RIS，并生成 Zotero 导入遗漏报告
- 提供 Zotero 导出检查 / 待复核面板，可按 skipped、unknown、document、needs_review、缺 DOI、缺作者筛选并批量修正
- 提供可选 AI 粗读 / 精读，支持 OpenAI-compatible API、可编辑模型名和 Base URL，API Key 仅从环境变量或本机临时输入读取
- 优化 GUI 信息架构：扫描区、整理/复核/导入工具组、右侧当前记录详情和下一步建议
- 支持批量复核、重复文献合并标记、重命名日志和撤销重命名
- 增强中文学位论文元数据提取：题名、作者、导师、学校、地点、年份
- 提供 GUI 和 CLI 两种使用方式

## GUI 使用

下载 Release 中的 `PDF文献管理器.zip`，解压后双击：

```text
PDF文献管理器.exe
```

推荐流程：

1. 选择 PDF 文件夹。
2. 点击“开始扫描”。
3. 双击列表项复核题名、作者、年份、学校/期刊、硕博类型。
4. 点击“导出索引 / 引用”。
5. 需要重命名时先生成“重命名计划”，确认后再“应用重命名”。
6. 需要批量修正时使用“批量复核”；重复条目使用“重复合并”生成合并标记。
7. 使用“Zotero 检查”查看本次可导入数量和 skipped 条目，必要时批量标为 `paper` 或 `thesis` 后重新导出。
8. 选中文献后点击“AI 阅读”，选择粗读/精读，按需修改模型、Base URL、环境变量名或临时 API Key。
9. 使用“导入 Zotero”“导入 Obsidian”完成外部软件导入；若 Zotero 条目不完整，可打开待复核面板或 `zotero_import_report.md`。
10. 重命名后可通过“撤销重命名”按日志恢复。

## CLI 使用

```powershell
.\pdf-manager-cli.exe "D:\PDFs"
.\pdf-manager-cli.exe "D:\PDFs" --style gbt7714 --no-network
.\pdf-manager-cli.exe "D:\PDFs" --style ieee --recursive
```

## 输出文件

扫描文件夹下会生成：

```text
_pdf_manager_output/
```

| 文件 | 作用 |
|---|---|
| `pdf_index.md` | Markdown PDF 总表 |
| `pdf_index.csv` | 表格索引 |
| `references_<style>.md` | 当前引用风格的引用列表 |
| `references.bib` | BibTeX 文献库 |
| `references.ris` | Zotero 兼容 RIS 导入文件 |
| `zotero_import_report.md` | Zotero 实际导入数量与被跳过记录说明 |
| `obsidian_notes/` | Obsidian 文献笔记 |
| `ai_reading_notes/` | AI 粗读/精读 Markdown 笔记 |
| `import_guide.md` | 第三方软件导入说明 |
| `duplicates.md` | 重复文献分组与合并标记 |
| `rename_log.jsonl` / `rename_log.md` | 重命名与撤销记录 |
| `session.json` | GUI 可重新加载的扫描结果 |

Obsidian 模板变量包括：`citekey`、`bibtex_key`、`zotero_key`、`title`、`authors`、`year`、`venue`、`school`、`place`、`doi`、`arxiv_id`、`citation`、`citation_gbt`、`citation_ieee`、`type`、`thesis_type`、`advisor`、`date_added`。

AI 阅读默认模型名为 `gpt-5.4`，可在窗口中改为任意 OpenAI-compatible 模型。API Key 不会写入配置、导出文件、日志或仓库；留空时读取环境变量 `OPENAI_API_KEY`，也可临时输入其他平台的 key。

## 开发

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
.\.venv\Scripts\pytest.exe .\tests -v
```

构建 Windows exe：

```powershell
.\build_exe.ps1
```
