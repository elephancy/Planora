"""Keep retained diagnostic fixtures outside normal product and CI execution.

This static boundary does not sanitize legacy exec or stdlib XML parsers.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path
import subprocess
import sys
import tempfile
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


def test_unverified_legacy_execution_is_disabled() -> None:
    """Exercise just each disabled helper, never import or replay an archive module."""
    root = Path(__file__).resolve().parents[1]
    count = 0
    for source in sorted((root / ARCHIVE).rglob("*.py")):
        text = source.read_text(encoding="utf-8")
        functions = [node for node in ast.parse(text).body
                     if isinstance(node, ast.FunctionDef) and node.name == "_execute_module"]
        for function in functions:
            count += 1
            body = function.body
            assert len(body) == 2 and isinstance(body[0], ast.Expr)
            assert isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str)
            assert isinstance(body[1], ast.Raise) and body[1].cause is None
            failure = body[1].exc
            assert isinstance(failure, ast.Call) and isinstance(failure.func, ast.Name)
            assert failure.func.id == "RuntimeError" and not failure.keywords
            assert len(failure.args) == 1 and isinstance(failure.args[0], ast.Constant)
            assert failure.args[0].value == "Unverified legacy module execution is disabled"
            assert not function.decorator_list
            assert not function.args.defaults and not function.args.kw_defaults
            with tempfile.TemporaryDirectory(prefix="disabled-legacy-helper-") as directory:
                sentinel = Path(directory) / "payload-executed"
                payload = ("from pathlib import Path; Path(" + repr(str(sentinel)) + ").write_text('unsafe')").encode()
                # The function body and signature were validated above. No archived
                # top-level code or payload is evaluated by the test harness.
                program = ("from __future__ import annotations\n" + ast.get_source_segment(text, function)
                           + "\ntry:\n    _execute_module('probe', 'fixture', " + repr(payload) + ")\n"
                           + "except RuntimeError as error:\n"
                           + "    assert str(error) == 'Unverified legacy module execution is disabled'\n"
                           + "    print('disabled')\n"
                           + "else:\n    raise AssertionError('legacy helper did not refuse')\n")
                result = subprocess.run([sys.executable, "-I", "-S", "-c", program],
                                        cwd=directory, stdin=subprocess.DEVNULL,
                                        capture_output=True, timeout=5, check=False)
                assert result.returncode == 0 and result.stdout == b"disabled\n" and not result.stderr
                assert not sentinel.exists(), "untrusted legacy payload executed"
    assert count == 12
