"""Обратная перекодировка .bat: cp866/CRLF -> UTF-8/LF (для правки текста).

Использовать после правок, когда нужно вернуть .bat в репозиторий в читаемом
виде; перед использованием снова прогнать bat_to_oem.py.

    python probe/bat_from_oem.py          # все *.bat в корне проекта
    python probe/bat_from_oem.py file.bat # конкретный файл
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def convert(path: Path) -> None:
    text = path.read_bytes().decode("cp866").replace("\r\n", "\n")
    path.write_bytes(text.encode("utf-8"))
    print(f"{path.name}: cp866/CRLF -> UTF-8/LF ({len(text)} символов)")


def main() -> None:
    targets = [Path(arg) for arg in sys.argv[1:]] or sorted(ROOT.glob("*.bat"))
    if not targets:
        raise SystemExit("не нашёл ни одного .bat")
    for target in targets:
        convert(target)


if __name__ == "__main__":
    main()
