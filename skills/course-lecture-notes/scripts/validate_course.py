"""Validate manifest paths and seven-artifact structure; does not validate content."""
import argparse
import json
from pathlib import Path

REQUIRED = {"视频时间轴", "中文精译逐字稿", "详细讲义", "一页复习", "闪卡与练习", "实验"}
STATUSES = {"pending", "sources_ready", "drafted", "reviewed", "complete", "blocked"}


def validate(root: Path) -> list[str]:
    errors = []
    manifest = root / "course-manifest.json"
    if not manifest.is_file():
        return ["Missing course-manifest.json"]
    try:
        data = json.loads(manifest.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError) as exc:
        return [f"Cannot read manifest: {exc}"]
    if not isinstance(data, dict):
        return ["Manifest must be a JSON object"]
    lessons = data.get("lessons")
    if not isinstance(lessons, list) or not lessons:
        return ["lessons must be a nonempty list"]
    ids, directories = set(), set()

    def local_path(value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("path must be a nonempty string")
        path = Path(value)
        if path.is_absolute():
            raise ValueError("path must be relative to course root")
        result = (root / path).resolve()
        if not result.is_relative_to(root):
            raise ValueError("path escapes course root")
        return result

    for index, lesson in enumerate(lessons, 1):
        if not isinstance(lesson, dict):
            errors.append(f"Lesson {index}: must be an object")
            continue
        code = lesson.get("id")
        if not isinstance(code, str) or not code or code in ids:
            errors.append(f"Lesson {index}: missing or duplicate id")
        else:
            ids.add(code)
        label = str(code or index)
        if lesson.get("status") not in STATUSES:
            errors.append(f"{label}: invalid status")
        if lesson.get("source_status") not in {"complete", "partial", "missing"}:
            errors.append(f"{label}: invalid source_status")
        try:
            directory = local_path(lesson.get("directory"))
            if directory in directories:
                errors.append(f"{label}: duplicate lesson directory")
            directories.add(directory)
            if not directory.is_dir():
                errors.append(f"{label}: lesson directory missing")
        except ValueError as exc:
            errors.append(f"{label}: {exc}")
            continue
        artifacts = lesson.get("artifacts", {})
        if not isinstance(artifacts, dict):
            errors.append(f"{label}: artifacts must be an object")
            continue
        missing = REQUIRED - artifacts.keys()
        if not ({"官方英文逐字稿", "官方原文逐字稿"} & artifacts.keys()):
            missing.add("官方原文或英文逐字稿")
        if missing:
            errors.append(f"{label}: missing artifacts: {', '.join(sorted(missing))}")
        paths = set()
        for name, value in artifacts.items():
            try:
                path = local_path(value)
                if not path.is_relative_to(directory):
                    raise ValueError("artifact outside assigned lesson directory")
                if path in paths:
                    raise ValueError("duplicate artifact path")
                paths.add(path)
                if not path.is_file() or not path.read_text(encoding="utf-8-sig").strip():
                    raise ValueError("artifact missing or empty")
            except (ValueError, OSError) as exc:
                errors.append(f"{label}/{name}: {exc}")
        if lesson.get("status") == "complete":
            if lesson.get("source_status") != "complete" or lesson.get("gaps"):
                errors.append(f"{label}: complete lesson still has source gaps")
            verification = lesson.get("verification", {})
            if not isinstance(verification, dict) or verification.get("coverage") != "passed":
                errors.append(f"{label}: complete lesson lacks coverage review")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    errors = validate(args.root.resolve())
    for error in errors:
        print(error)
    print("STRUCTURE FAILED" if errors else "STRUCTURE PASSED (content review still required)")
    raise SystemExit(bool(errors))


if __name__ == "__main__":
    main()
