"""映刻 · 短视频实时推荐系统 —— 本地一键启动脚本。

在 PyCharm 里直接右键本文件 → Run / Debug 即可，不需要敲任何命令：

  1. 自动切换到仓库根目录，保证 frontend/、runtime/ 等相对路径正确；
  2. 自动读取仓库根目录的 .env（没有时按 demo + 本地 SQLite 兜底）；
  3. 用 uvicorn 启动 FastAPI，并在终端打印访问地址；
  4. 稍等片刻自动打开浏览器到 http://127.0.0.1:8000 。

调试建议：在本文件里下断点只能停在启动过程；要看请求逻辑，
请把断点打在 backend/main.py 的路由函数里，然后用 Debug 方式运行本文件。
"""

from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOST = os.getenv("APP_HOST", "127.0.0.1")
PORT = int(os.getenv("APP_PORT", "8000"))
URL = f"http://{HOST}:{PORT}"


def prepare() -> None:
    """把运行环境准备好：工作目录、模块路径、.env、运行目录。"""
    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    env_file = ROOT / ".env"
    if env_file.is_file():
        try:
            from dotenv import load_dotenv
        except ImportError:  # 依赖没装时给出明确提示，而不是神秘失败
            sys.exit(
                "缺少 python-dotenv。请先执行：\n"
                f'  "{ROOT / ".venv" / "Scripts" / "python.exe"}" -m pip install python-dotenv'
            )
        load_dotenv(env_file, override=False)
        print(f"[映刻] 已加载配置 {env_file.name}")
    else:
        print("[映刻] 未找到 .env，使用内置演示配置")

    # 兜底：本机没有 MySQL 时也能跑起来
    os.environ.setdefault("REC_MODE", "demo")
    os.environ.setdefault("BUSINESS_BACKEND", "sqlite")

    mode = os.environ["REC_MODE"]
    backend = os.environ["BUSINESS_BACKEND"]
    if mode == "production" and backend != "mysql":
        sys.exit("[映刻] production 模式必须使用 MySQL；请把 BUSINESS_BACKEND 设为 mysql 并填好 .env")

    (ROOT / "runtime").mkdir(parents=True, exist_ok=True)
    Path(os.environ.get("MODEL_DIRECTORY", ROOT / "runtime" / "models")).mkdir(parents=True, exist_ok=True)
    Path(os.environ.get("MEDIA_DIRECTORY", ROOT / "runtime" / "media")).mkdir(parents=True, exist_ok=True)

    print(f"[映刻] 录模式={mode}，业务存储={backend}")


def open_browser_later(delay: float = 2.0) -> None:
    def worker() -> None:
        time.sleep(delay)
        try:
            webbrowser.open(URL)
        except Exception:
            pass

    threading.Thread(target=worker, daemon=True).start()


def main() -> None:
    prepare()
    import uvicorn

    print(f"[映刻] 启动中…… 首页 {URL}    接口文档 {URL}/docs")
    open_browser_later()
    uvicorn.run("backend.main:app", host=HOST, port=PORT, reload=False, log_level="info", access_log=True)


if __name__ == "__main__":
    main()
