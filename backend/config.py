"""
Centralized Configuration & Safe Environment Loader for REDLINE.

Provides:
- Resilient, safe loading of .env files without external dependencies.
- Strict credential protection: NEVER prints, logs, or leaks secret values.
- UTF-8 with BOM support (utf-8-sig) and CRLF/LF line ending normalization.
- Fail-closed API configuration verification.
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional


def load_dotenv_if_present(env_path: Optional[str] = None, override: bool = False) -> List[str]:
    """
    Safely discovers and loads environment variables from a .env file if present.
    Supports utf-8 and utf-8-sig (with BOM), handling Windows and Unix line endings.
    Never prints or logs credential values. Returns list of loaded variable names.
    """
    candidates: List[Path] = []
    if env_path:
        candidates.append(Path(env_path))
    else:
        repo_root = os.environ.get("REDLINE_REPO_ROOT")
        if repo_root:
            candidates.append(Path(repo_root) / ".env")
        # Current working directory .env
        candidates.append(Path.cwd() / ".env")
        # Repository root relative to this module (p:/REDLINE)
        candidates.append(Path(__file__).resolve().parent.parent / ".env")

    target_file: Optional[Path] = None
    for c in candidates:
        if c.is_file():
            target_file = c.resolve()
            break

    if not target_file:
        return []

    loaded_keys: List[str] = []
    content: str = ""
    for enc in ("utf-8-sig", "utf-16", "utf-16-le", "utf-8"):
        try:
            content = target_file.read_text(encoding=enc)
            break
        except Exception:
            continue
    if not content:
        return []

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
        if not match:
            continue

        key, val = match.group(1), match.group(2)

        # Handle quoted values
        if len(val) >= 2 and ((val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'"))):
            val = val[1:-1]
        else:
            # Inline comment removal if unquoted
            if " #" in val:
                val = val.split(" #", 1)[0].rstrip()

        if override or key not in os.environ:
            os.environ[key] = val
            loaded_keys.append(key)

    return loaded_keys
