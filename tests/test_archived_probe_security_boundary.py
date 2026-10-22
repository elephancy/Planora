"""Keep retained diagnostic fixtures outside normal product and CI execution.

This static boundary does not sanitize legacy exec or stdlib XML parsers.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path
import tomllib

ARCHIVE = "benchmarks/probe_diagnostics"
UNSAFE_SYMBOLS = ("_execute_module", "agh_child_acceptance", "validate_solution_document_bytes")
PRODUCT_ROOTS = ("api", "core", "product", "services", "ui", "utils", "web")
SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".sh", ".ps1", ".yml", ".yaml"}
OWN_NAME = "test_archived_probe_security_boundary.py"


def assert_archived_probe_boundary(root: Path) -> dict[str, int]:
    archive = root / ARCHIVE
    assert archive.is_dir(), "frozen probe archive missing"
    helpers = []
    for source in archive.rglob("*.py"):
        tree = ast.parse(source.read_bytes())
        defined = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_execute_module"]
        if defined:
            helpers.append(source)
            assert not any(
                isinstance(n, ast.Name) and n.id == "_execute_module"
                or isinstance(n, ast.Attribute) and n.attr == "_execute_module"
                for n in ast.walk(tree)
            ), f"legacy helper acquired a call/reference: {source.relative_to(root)}"
    assert len(helpers) == 12, "legacy helper inventory changed; review required"
    manual_entries = set()
    for source in (root / "scripts").rglob("*"):
        if source.is_file() and source.suffix in SOURCE_SUFFIXES:
            text = source.read_text(encoding="utf-8-sig")
            if "probe_diagnostics" in text or any(symbol in text for symbol in UNSAFE_SYMBOLS):
                manual_entries.add(source.name)
    while True:
        expanded = set(manual_entries)
        for source in (root / "scripts").rglob("*"):
            if source.is_file() and source.suffix in SOURCE_SUFFIXES:
                text = source.read_text(encoding="utf-8-sig")
                if any(name in text for name in manual_entries):
                    expanded.add(source.name)
        if expanded == manual_entries:
            break
        manual_entries = expanded
    def product_sources(directory):
        for current, directories, files in os.walk(directory):
            directories[:] = [name for name in directories
                              if name not in {"node_modules", "dist", ".venv", "__pycache__", ".git"}]
            yield from (Path(current) / name for name in files if Path(name).suffix in SOURCE_SUFFIXES)

    checked = set()
    for directory in PRODUCT_ROOTS:
        if (root / directory).is_dir():
            checked.update(product_sources(root / directory))
    checked.add(root / "main.py")
    checked.update((root / ".github/workflows").glob("*.yml"))
    checked.update((root / ".github/workflows").glob("*.yaml"))
    checked.update(root / path for path in (
        "scripts/run_ci_checks.sh", "scripts/smoke/run_packaged_engine_smoke.py",
        "scripts/unix/build_installer.sh", "scripts/windows/build_installer.ps1"))
    ordinary_tests = [p for p in (root / "tests").rglob("test_*.py")
                      if p.name != OWN_NAME
                      and not p.match("test_run_muni_v*.py")
                      and p.name != "test_muni_v33_terminal_gate_rejection.py"]
    checked.update(ordinary_tests)
    forbidden = ("probe_diagnostics", *UNSAFE_SYMBOLS, *manual_entries)
    for source in sorted(checked):
        assert source.is_file(), f"normal entry missing: {source.relative_to(root)}"
        text = source.read_text(encoding="utf-8-sig")
        assert not any(token in text for token in forbidden), (
            f"normal product/CI source references offline probe authority: {source.relative_to(root)}"
        )
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests"]
    pipeline = (root / "scripts/run_ci_checks.sh").read_text(encoding="utf-8")
    assert "find tests -type f -name 'test_*.py'" in pipeline
    assert "! -name 'test_run_muni_v*.py'" in pipeline
    assert "! -name 'test_muni_v33_terminal_gate_rejection.py'" in pipeline
    return {"dormant_helpers": len(helpers), "normal_sources_checked": len(checked),
            "ordinary_tests_checked": len(ordinary_tests), "manual_script_names": len(manual_entries)}


def test_archived_probes_stay_outside_product_and_normal_ci() -> None:
    assert_archived_probe_boundary(Path(__file__).resolve().parents[1])
