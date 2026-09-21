"""Проверка, что все символы .bat влезают в cp866 (кодировку русской консоли)."""

from __future__ import annotations

from pathlib import Path


def main() -> None:
    for path in sorted(Path(".").glob("*.bat")):
        text = path.read_text(encoding="utf-8")
        bad = []
        for char in sorted(set(text)):
            try:
                char.encode("cp866")
            except UnicodeEncodeError:
                bad.append(char)
        if bad:
            print(f"{path.name}: НЕ влезают: {bad}")
        else:
            print(f"{path.name}: OK")


if __name__ == "__main__":
    main()
