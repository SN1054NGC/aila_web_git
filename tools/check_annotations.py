#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка аннотаций типов: что размечено, а что нет.

    python tools/check_annotations.py [каталог]

Показывает по каждому файлу функции без аннотаций аргументов и без возвращаемого типа,
а также итоговую долю размеченного кода.
"""
from __future__ import annotations

import ast
import sys
from collections.abc import Iterator
from pathlib import Path

SKIP_DIRS = {".venv", ".venv_311", "venv", "__pycache__", "models", "rag_db", "uploads", "logs",
             "snapshots", "repo", "repo_tmp", "site-packages", "node_modules", "re-store"}


def functions(tree: ast.AST) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def check_file(path: Path) -> tuple[int, int, list[str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        return 0, 0, [f"СИНТАКСИС: {exc}"]
    total = annotated = 0
    problems: list[str] = []
    for func in functions(tree):
        total += 1
        missing: list[str] = []
        if func.returns is None:
            missing.append("нет возвращаемого типа")
        args = list(func.args.posonlyargs) + list(func.args.args) + list(func.args.kwonlyargs)
        args = [a for a in args if a.arg not in ("self", "cls")]
        untyped = [a.arg for a in args if a.annotation is None]
        if untyped:
            missing.append("без типа: " + ", ".join(untyped))
        if func.args.vararg and func.args.vararg.annotation is None:
            missing.append("без типа: *" + func.args.vararg.arg)
        if func.args.kwarg and func.args.kwarg.annotation is None:
            missing.append("без типа: **" + func.args.kwarg.arg)
        if not missing:
            annotated += 1
        else:
            problems.append(f"  строка {func.lineno:4}  {func.name}()  ->  {'; '.join(missing)}")
    return total, annotated, problems


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
    files = []
    for path in sorted(root.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        files.append(path)

    grand_total = grand_done = 0
    for path in files:
        total, done, problems = check_file(path)
        if not total:
            if problems:
                print(f"{path.relative_to(root)}: {problems[0]}")
            continue
        grand_total += total
        grand_done += done
        mark = "OK " if done == total else "…  "
        print(f"{mark}{str(path.relative_to(root)):34} размечено {done}/{total}")
        for line in problems:
            print(line)

    percent = (grand_done / grand_total * 100) if grand_total else 0
    print("-" * 62)
    print(f"ИТОГО: {grand_done} из {grand_total} функций полностью размечены ({percent:.0f}%)")
    return 0 if grand_done == grand_total else 1


if __name__ == "__main__":
    sys.exit(main())
