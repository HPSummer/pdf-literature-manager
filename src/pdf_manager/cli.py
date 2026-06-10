import argparse
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pdf-manager",
        description="One-click PDF management tool",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Directory to scan (default: directory of executable/script)",
    )
    parser.add_argument("--config", metavar="CONFIG_YAML", default=None)
    parser.add_argument("--no-network", action="store_true")
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument(
        "--style",
        choices=["ieee", "apa", "mla", "chicago", "gbt7714"],
        default=None,
        help="Citation style for generated Markdown references",
    )
    parser.add_argument(
        "--rename-plan",
        action="store_true",
        help="Generate rename_plan.md without renaming files",
    )
    parser.add_argument(
        "--sample-regression",
        metavar="SAMPLES_DIR",
        default=None,
        help="Run recognition regression on a directory of sample PDFs and write a report",
    )
    return parser.parse_args()
