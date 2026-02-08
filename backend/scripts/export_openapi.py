from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app


def main() -> None:
    spec = app.openapi()
    output = Path("/Users/praty/hepatica-p/docs/openapi.generated.json")
    output.write_text(json.dumps(spec, indent=2))
    print(f"OpenAPI spec exported to {output}")


if __name__ == "__main__":
    main()
