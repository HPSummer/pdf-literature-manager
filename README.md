# PDF 文献管理器

Windows 一键 PDF 文献管理工具，面向论文、硕士/博士学位论文和普通 PDF 的整理、引用、重命名与 Obsidian 知识库归档。

## 功能

- 自动扫描当前文件夹或指定文件夹中的 PDF
- 识别期刊/会议论文、硕士论文、博士论文、普通 PDF 和待复核文件
- 默认按 GB/T 7714 生成引用和安全文件名
- 支持 IEEE、APA、MLA、Chicago、GB/T 7714
- 生成 `references.bib`、`references.ris`、Markdown 引用列表和 CSV/JSON 索引
- 生成 Obsidian 文献笔记，并可一键复制到 vault 的 `02_literature`
- 支持 Zotero、小绿鲸等文献管理软件导入 BibTeX/RIS
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
6. 使用“导入 Zotero”“导入 Obsidian”“导入小绿鲸”完成外部软件导入。

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
| `references.ris` | Zotero/小绿鲸兼容 RIS 导入文件 |
| `obsidian_notes/` | Obsidian 文献笔记 |
| `import_guide.md` | 第三方软件导入说明 |
| `session.json` | GUI 可重新加载的扫描结果 |

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

