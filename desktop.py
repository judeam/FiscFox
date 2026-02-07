#!/usr/bin/env python3
"""
FiscFox Desktop Application

Cross-platform desktop wrapper using PyWebView.
Runs the FastAPI server in a background thread and displays it in a native window.

Usage:
    python desktop.py              # Run desktop app
    python desktop.py --debug      # Run with DevTools enabled

Packaging:
    pyinstaller fiscfox.spec       # Build standalone executable
"""

import argparse
import os
import platform
import signal
import socket
import sys
import threading
import time
from pathlib import Path


def find_free_port(start: int = 8000, end: int = 9000) -> int:
    """Find an available port in the given range."""
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found in range {start}-{end}")


def get_data_dir() -> Path:
    """Get platform-appropriate data directory."""
    app_name = "FiscFox"

    if platform.system() == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif platform.system() == "Darwin":  # macOS
        base = Path.home() / "Library" / "Application Support"
    else:  # Linux and others
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

    data_dir = base / app_name
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def start_server(port: int, data_dir: Path) -> None:
    """Start the FastAPI server in the background."""
    import uvicorn

    # Set environment variables for the app
    os.environ["FISCFOX_DATA_DIR"] = str(data_dir)
    os.environ["FISCFOX_DB_PATH"] = str(data_dir / "fiscfox.db")
    os.environ["FISCFOX_DESKTOP_MODE"] = "1"

    # Import after setting env vars
    from src.main import app

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    server.run()


def wait_for_server(port: int, timeout: float = 10.0) -> bool:
    """Wait for the server to become available."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect(("127.0.0.1", port))
                return True
        except OSError:
            time.sleep(0.1)
    return False


def main() -> None:
    """Main entry point for desktop application."""
    parser = argparse.ArgumentParser(description="FiscFox Desktop Application")
    parser.add_argument("--debug", action="store_true", help="Enable DevTools")
    parser.add_argument("--port", type=int, default=0, help="Specific port (0 = auto)")
    args = parser.parse_args()

    # Import webview here to allow running without it installed (for server-only mode)
    try:
        import webview
    except ImportError:
        print("Error: pywebview not installed. Run: pip install pywebview")
        sys.exit(1)

    # Find data directory and free port
    data_dir = get_data_dir()
    port = args.port if args.port else find_free_port()

    print(f"FiscFox Desktop")
    print(f"  Data: {data_dir}")
    print(f"  Port: {port}")

    # Start server in background thread
    server_thread = threading.Thread(
        target=start_server,
        args=(port, data_dir),
        daemon=True,
        name="FiscFox-Server"
    )
    server_thread.start()

    # Wait for server to be ready
    if not wait_for_server(port):
        print("Error: Server failed to start")
        sys.exit(1)

    # Find icon path
    icon_path = None
    for icon_name in ["assets/icon.png", "fiscfox_logo_transparent.png", "fiscfox_logo.png"]:
        candidate = Path(__file__).parent / icon_name
        if candidate.exists():
            icon_path = str(candidate)
            break

    # Create native window
    window = webview.create_window(
        title="FiscFox - Tax Management",
        url=f"http://127.0.0.1:{port}",
        width=1280,
        height=800,
        min_size=(800, 600),
        resizable=True,
        frameless=False,
        easy_drag=False,
        text_select=True,
    )

    # Handle graceful shutdown
    def on_closed() -> None:
        os.kill(os.getpid(), signal.SIGTERM)

    window.events.closed += on_closed

    # Start the GUI event loop
    webview.start(debug=args.debug)


if __name__ == "__main__":
    main()
