"""Read-only format and saved execution-state check; does not execute code."""
import argparse
import json
from pathlib import Path

import nbformat


def inspect(path, require_executed=False):
    notebook = nbformat.read(path, as_version=4)
    nbformat.validate(notebook)
    code_cells = [cell for cell in notebook.cells if cell.cell_type == "code" and cell.source.strip()]
    pending = [i + 1 for i, cell in enumerate(notebook.cells)
               if cell.cell_type == "code" and cell.source.strip() and cell.execution_count is None]
    errors = [i + 1 for i, cell in enumerate(notebook.cells) if cell.cell_type == "code"
              and any(out.get("output_type") == "error" for out in cell.get("outputs", []))]
    output_cells = sum(bool(cell.get("outputs")) for cell in code_cells)
    issues = []
    if not code_cells:
        issues.append("No nonempty code cells")
    if errors:
        issues.append("Saved runtime errors present")
    if require_executed and pending:
        issues.append("Some code cells have no saved execution count")
    if require_executed and code_cells and not output_cells:
        issues.append("No saved outputs to inspect")
    return {"file": str(path), "cells": len(notebook.cells), "code_cells": len(code_cells),
            "cells_with_outputs": output_cells, "unexecuted_cell_numbers": pending,
            "error_cell_numbers": errors, "issues": issues,
            "limits": "Checks saved state only; no freshness, behavior, content or visual validation."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("notebook", type=Path)
    parser.add_argument("--require-executed", action="store_true")
    args = parser.parse_args()
    try:
        result = inspect(args.notebook, args.require_executed)
    except (OSError, ValueError, nbformat.ValidationError) as exc:
        parser.exit(1, f"Notebook check failed: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(bool(result["issues"]))


if __name__ == "__main__":
    main()
