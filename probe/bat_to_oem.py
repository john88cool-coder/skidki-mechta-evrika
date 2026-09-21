"""Перекодировка .bat в OEM 866 с CRLF (как ждёт консоль русской Windows).

cmd.exe читает .bat в текущей кодовой странице консоли - на русской Windows
это 866. Файлы пишутся в UTF-8 и с LF при разработке, поэтому перед
использованием их нужно конвертировать: иначе echo с русским текстом выводит
кракозябры, а goto по меткам может сбиться.

    python probe/bat_to_oem.py            # все *.bat в корне проекта
    python probe/bat_to_oem.py file.bat   # конкретный файл

Обратно (для правки текста) - bat_from_oem.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def convert(path: Path) -> None:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    path.write_bytes(text.replace("\n", "\r\n").encode("cp866"))
    print(f"{path.name}: UTF-8/LF -> cp866/CRLF ({len(text)} символов)")


def main() -> None:
    targets = [Path(arg) for arg in sys.argv[1:]] or sorted(ROOT.glob("*.bat"))
    if not targets:
        raise SystemExit("не нашёл ни одного .bat")
    for target in targets:
        convert(target)


if __name__ == "__main__":
    main()
