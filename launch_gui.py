from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    project_dir: Path = Path(__file__).resolve().parent
    src_dir: Path = project_dir / "src"
    if not src_dir.exists():
        raise RuntimeError(f"Source directory does not exist: {src_dir}")
    sys.path.insert(0, str(src_dir))

    from gpm_selenium.gui import main as gui_main

    gui_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
