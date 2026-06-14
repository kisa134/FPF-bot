"""Launch FPF Studio:  python -m v1.web  (then open http://127.0.0.1:8000)."""

from __future__ import annotations

import os


def main() -> None:
    import uvicorn

    host = os.environ.get("FPF_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("FPF_WEB_PORT", "8000"))
    print(f"FPF Studio → http://{host}:{port}")
    uvicorn.run("v1.web.server:app", host=host, port=port)


if __name__ == "__main__":
    main()
