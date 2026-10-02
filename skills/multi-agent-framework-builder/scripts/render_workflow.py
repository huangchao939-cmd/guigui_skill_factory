"""Generate definition-derived Mermaid dependencies. Does not render images."""
import argparse
import json
from pathlib import Path
from validate_v2 import dependency_graph, rules


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--overwrite", action="store_true", help="explicitly replace an existing generated graph")
    args = parser.parse_args()
    workflow = json.loads((args.root / "workflow.json").read_text(encoding="utf-8-sig"))
    rules.validate_definition(workflow, args.root)
    root = args.root.resolve()
    path = (root / "diagrams/dependencies.mmd").resolve()
    rules.require(path.is_relative_to(root), "graph path escapes root")
    content = dependency_graph(workflow)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        print("Graph already current")
        return
    rules.require(not path.exists() or args.overwrite, "graph exists; use --overwrite after reviewing change")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    print(path)


if __name__ == "__main__":
    main()
