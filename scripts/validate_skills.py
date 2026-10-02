"""Check catalog, skill metadata, Python syntax and local Markdown references."""
import ast
import json
import re
from pathlib import Path
from urllib.parse import unquote

import yaml

ROOT = Path(__file__).resolve().parents[1]


def main():
    errors = []
    data = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
    entries = data.get("skills", [])
    if not entries:
        errors.append("Catalog is empty")
    names = set()
    listed_paths = set()
    for entry in entries:
        name = entry.get("name", "")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or len(name) > 64:
            errors.append(f"Invalid name: {name}")
        if name in names:
            errors.append(f"Duplicate name: {name}")
        names.add(name)
        path = (ROOT / entry.get("path", "")).resolve()
        if path.parent != (ROOT / "skills").resolve() or path.name != name:
            errors.append(f"Invalid skill path: {name}")
            continue
        listed_paths.add(path)
        if not re.fullmatch(r"\d+\.\d+\.\d+", entry.get("version", "")):
            errors.append(f"Invalid version: {name}")
        if entry.get("status") not in {"draft", "active", "deprecated"}:
            errors.append(f"Invalid status: {name}")
        verification = entry.get("verification", {})
        if not verification.get("checks") or "limitations" not in verification:
            errors.append(f"Missing verification record: {name}")
        skill_md = path / "SKILL.md"
        if not skill_md.is_file():
            errors.append(f"Missing SKILL.md: {name}")
            continue
        text = skill_md.read_text(encoding="utf-8")
        match = re.match(r"\A---\n(.*?)\n---(?:\n|$)", text, re.S)
        if not match:
            errors.append(f"Missing frontmatter: {name}")
            continue
        metadata = yaml.safe_load(match.group(1))
        if not isinstance(metadata, dict) or metadata.get("name") != name:
            errors.append(f"Frontmatter name mismatch: {name}")
            continue
        if not isinstance(metadata.get("description"), str) or not metadata["description"].strip():
            errors.append(f"Missing description: {name}")
        for script in path.rglob("*.py"):
            try:
                ast.parse(script.read_text(encoding="utf-8"), filename=str(script))
            except SyntaxError as exc:
                errors.append(f"Python syntax: {script.relative_to(ROOT)}: {exc}")
        ui_path = path / "agents" / "openai.yaml"
        if ui_path.exists():
            ui = yaml.safe_load(ui_path.read_text(encoding="utf-8"))
            prompt = (ui or {}).get("interface", {}).get("default_prompt")
            if prompt and f"${name}" not in prompt:
                errors.append(f"Default prompt missing skill invocation: {name}")
    actual_paths = {p.resolve() for p in (ROOT / "skills").iterdir() if p.is_dir()}
    for path in actual_paths - listed_paths:
        errors.append(f"Unlisted skill: {path.name}")
    for md in ROOT.rglob("*.md"):
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", md.read_text(encoding="utf-8")):
            if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", target) or target.startswith("#"):
                continue
            target = unquote(target.split("#", 1)[0].strip("<>"))
            if target and not (md.parent / target).exists():
                errors.append(f"Broken link: {md.relative_to(ROOT)} -> {target}")
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        raise SystemExit(1)
    print(f"Validated {len(entries)} skill(s): metadata, catalog, Python syntax and Markdown references")
    print("Content and runtime behavior require task-specific verification.")


if __name__ == "__main__":
    main()
