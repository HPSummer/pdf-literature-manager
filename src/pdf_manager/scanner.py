from pathlib import Path


def scan(directory: str, recursive: bool = False) -> list[dict]:
    root = Path(directory)
    pattern = "**/*.pdf" if recursive else "*.pdf"
    results = []
    for p in root.glob(pattern):
        if p.is_file():
            results.append({"path": p, "file_size": p.stat().st_size})
    return results
