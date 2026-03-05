from pathlib import Path
import sys

MARKERS = ("<<<<<<<", "=======", ">>>>>>>")


def has_conflict_marker(path: Path) -> bool:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False
    return any(marker in content for marker in MARKERS)


def main() -> int:
    roots = [Path("templates"), Path("app.py")]
    offenders: list[Path] = []

    for root in roots:
        if root.is_file():
            if has_conflict_marker(root):
                offenders.append(root)
            continue
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and has_conflict_marker(path):
                offenders.append(path)

    if offenders:
        print("Found unresolved merge conflict markers in:")
        for path in offenders:
            print(f" - {path}")
        return 1

    print("No merge conflict markers found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
