#!/usr/bin/env python
"""
Everlay Remote Service - Android Foreground Service
Runs FastAPI server in background for remote control.
"""
import os
import sys
import asyncio
import threading
import time
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

# Set Android-specific environment
os.environ.setdefault('ANDROID_PRIVATE', os.environ.get('ANDROID_PRIVATE', '/data/user/0/org.everlay.everlay/files'))
os.environ.setdefault('RAG_DB_PATH', os.path.join(os.environ.get('ANDROID_PRIVATE', '/data/user/0/org.everlay.everlay/files'), 'everlay_brain.db'))
os.environ.setdefault('DATABASE_URL', f'sqlite:///{os.environ.get("ANDROID_PRIVATE", "/data/user/0/org.everlay.everlay/files")}/everlay.db')
os.environ.setdefault('LOG_FILE', os.path.join(os.environ.get('ANDROID_PRIVATE', '/data/user/0/org.everlay.everlay/files'), 'logs', 'remote_service.log'))
os.environ.setdefault('APP_ENV', 'production')
os.environ.setdefault('APP_DEBUG', 'false')
os.environ.setdefault('WEB_HOST', '127.0.0.1')
os.environ.setdefault('WEB_PORT', '8000')

# Ensure directories exist
private_dir = Path(os.environ.get('ANDROID_PRIVATE', '/data/user/0/org.everlay.everlay/files'))
(private_dir / 'logs').mkdir(parents=True, exist_ok=True)

def run_fastapi_server():
    """Run FastAPI server in a separate thread."""
    import uvicorn
    from api.main import app

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)

    # Run in new event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(server.serve())


def run_foreground_service():
    """Run as Android foreground service."""
    # Import Android service modules
    try:
        from android import AndroidService
        from jnius import autoclass

        PythonService = autoclass('org.kivy.android.PythonService')
        service = PythonService.mService

        # Start FastAPI server in background thread
        server_thread = threading.Thread(target=run_fastapi_server, daemon=True)
        server_thread.start()

        # Give server time to start
        time.sleep(2)

        # Create foreground notification
        if hasattr(service, 'startForeground'):
            from android.notification import NotificationBuilder
            notification = NotificationBuilder() \
                .setTitle("Everlay Remote") \
                .setContent("Remote control server running") \
                .setSmallIcon("icon") \
                .setOngoing(True) \
                .build()
            service.startForeground(1001, notification)

        # Keep service alive
        while True:
            time.sleep(10)

    except Exception as e:
        print(f"Foreground service error: {e}")
        # Fallback: just run server
        run_fastapi_server()


if __name__ == '__main__':
    # Check if running on Android
    if hasattr(sys, 'getandroidapilevel'):
        run_foreground_service()
    else:
        # Desktop mode - just run server
        print("Running in desktop mode")
        run_fastapi_server()