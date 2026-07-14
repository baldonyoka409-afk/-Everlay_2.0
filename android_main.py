"""
Everlay Android Entry Point
Starts FastAPI server in background and launches Kivy WebView app.
With foreground service for background operation.
"""
import os
import sys
import asyncio
import threading
import time
import logging
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

# Set up Android-specific paths BEFORE importing config
if hasattr(sys, 'getandroidapilevel'):
    # Running on Android
    ANDROID_PRIVATE = Path(os.environ.get('ANDROID_PRIVATE', '/data/user/0/org.everlay/files'))
    ANDROID_APP_PATH = Path(os.environ.get('ANDROID_APP_PATH', '/data/app/~~'))

    # Override paths for Android
    os.environ['RAG_DB_PATH'] = str(ANDROID_PRIVATE / 'everlay_brain.db')
    os.environ['DATABASE_URL'] = f'sqlite:///{ANDROID_PRIVATE}/everlay.db'
    os.environ['LOG_FILE'] = str(ANDROID_PRIVATE / 'logs' / 'agents.log')
    os.environ['APP_ENV'] = 'production'
    os.environ['APP_DEBUG'] = 'false'
    os.environ['WEB_HOST'] = '127.0.0.1'
    os.environ['WEB_PORT'] = '8000'
    os.environ['WEB_PORT'] = '8000'

    # Ensure directories exist
    (ANDROID_PRIVATE / 'logs').mkdir(parents=True, exist_ok=True)
    (ANDROID_PRIVATE / 'web').mkdir(parents=True, exist_ok=True)

# Now import after environment setup
from core.config import get_settings
from core.logging_config import setup_logging
from api.main import app
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global server reference
_server_thread = None
_server_started = threading.Event()
_loop = None
_server_instance = None


def run_server():
    """Run uvicorn server in a separate thread with its own event loop."""
    global _loop, _server_instance
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)

    settings = get_settings()

    # On Android, bind to localhost only
    host = "127.0.0.1"
    port = int(os.environ.get('WEB_PORT', '8000'))

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
        loop="asyncio",
        access_log=False,
    )
    server = uvicorn.Server(config)
    _server_instance = server

    # Signal that server is starting
    _server_started.set()

    # Run server
    try:
        _loop.run_until_complete(server.serve())
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        _loop.close()


def start_server_thread():
    """Start FastAPI server in background thread."""
    global _server_thread
    if _server_thread is None or not _server_thread.is_alive():
        _server_started.clear()
        _server_thread = threading.Thread(target=run_server, daemon=True, name="FastAPI-Server")
        _server_thread.start()
        # Wait for server to start
        _server_started.wait(timeout=15)
        time.sleep(1.5)  # Give it time to bind
        logger.info("FastAPI server started on http://127.0.0.1:8000")


def stop_server():
    """Stop the FastAPI server."""
    global _server_instance, _loop
    if _server_instance:
        _server_instance.should_exit = True
    if _loop and _loop.is_running():
        _loop.call_soon_threadsafe(_loop.stop)


# Kivy App with WebView
from kivy.app import App
from kivy.clock import Clock
from kivy.logger import Logger
from kivy.utils import platform

if platform == 'android':
    from jnius import autoclass, cast
    from android.runnable import run_on_ui_thread
    from android import activity
    from android import PythonActivity
    from android.service import AndroidService

    WebView = autoclass('android.webkit.WebView')
    WebViewClient = autoclass('android.webkit.WebViewClient')
    WebSettings = autoclass('android.webkit.WebSettings')
    WebChromeClient = autoclass('android.webkit.WebChromeClient')
    ViewGroup = autoclass('android.view.ViewGroup')
    LinearLayout = autoclass('android.widget.LinearLayout')
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    Context = autoclass('android.content.Context')
    NotificationCompat = autoclass('androidx.core.app.NotificationCompat')
    NotificationManagerCompat = autoclass('androidx.core.app.NotificationManagerCompat')
    Intent = autoclass('android.content.Intent')
    PendingIntent = autoclass('android.app.PendingIntent')
    Build = autoclass('android.os.Build')
    PowerManager = autoclass('android.os.PowerManager')
    Settings = autoclass('android.provider.Settings')


class EverlayWebViewClient(WebViewClient):
    """WebViewClient that keeps navigation inside the WebView."""

    def shouldOverrideUrlLoading(self, view, request):
        url = request.getUrl().toString() if hasattr(request, 'getUrl') else request.toString()
        # Allow all URLs to load in WebView
        return False

    def onPageFinished(self, view, url):
        Logger.info(f"Everlay: Page loaded: {url}")

    def onReceivedError(self, view, request, error):
        Logger.error(f"Everlay: WebView error: {error}")


class EverlayWebChromeClient(WebChromeClient):
    """WebChromeClient for console logs, alerts, permissions."""

    def onConsoleMessage(self, console_message):
        Logger.debug(f"WebView Console: {console_message.message()} (line {console_message.lineNumber()})")
        return True


class EverlayAndroidApp(App):
    """Kivy app that shows WebView pointing to local FastAPI server."""

    webview = None
    _server_started = False
    _notification_id = 1001
    _foreground_service = None
    _remote_ws = None

    def build(self):
        """Build the app UI - WebView on Android, placeholder on desktop."""
        Logger.info("Everlay: Building Android app")

        if platform == 'android':
            return self._create_webview()
        else:
            # Desktop fallback
            from kivy.uix.label import Label
            from kivy.uix.button import Button
            from kivy.uix.boxlayout import BoxLayout

            layout = BoxLayout(orientation='vertical', padding=20, spacing=10)
            layout.add_widget(Label(
                text="Everlay Android App\n\nThis is a desktop preview.\nOn Android, a WebView will open.\n\nServer: http://127.0.0.1:8000",
                halign='center',
                valign='middle'
            ))
            btn = Button(text="Start Server", size_hint_y=None, height=50)
            btn.bind(on_press=self._start_server_desktop)
            layout.add_widget(btn)
            return layout

    def _create_webview(self):
        """Create and configure WebView for Android."""
        # Create WebView
        self.webview = WebView(activity)

        # Enable JavaScript and settings
        settings = self.webview.getSettings()
        settings.setJavaScriptEnabled(True)
        settings.setDomStorageEnabled(True)
        settings.setAllowFileAccess(True)
        settings.setAllowContentAccess(True)
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW)
        settings.setCacheMode(WebSettings.LOAD_DEFAULT)
        settings.setBuiltInZoomControls(True)
        settings.setDisplayZoomControls(False)
        settings.setSupportMultipleWindows(True)
        settings.setJavaScriptCanOpenWindowsAutomatically(True)

        # Add JavaScript interface for remote control
        from jnius import autoclass, PythonJavaClass, java_method
        from android.runnable import run_on_ui_thread

        class RemoteControlInterface(PythonJavaClass):
            __javainterfaces__ = ['android/webkit/JavascriptInterface']

            def __init__(self, app):
                super().__init__()
                self.app = app

            @java_method('(Ljava/lang/String;)V')
            def sendToRemote(self, message):
                """Called from JavaScript to send message to remote WebSocket."""
                if self.app._remote_ws and not self.app._remote_ws.closed:
                    import asyncio
                    asyncio.create_task(self.app._remote_ws.send(message))

            @java_method('()V')
            def onRemoteConnected(self):
                """Called when remote WebSocket connects."""
                Logger.info("Everlay: Remote control connected")

            @java_method('(Ljava/lang/String;)V')
            def onRemoteMessage(self, message):
                """Handle message from remote."""
                Logger.info(f"Everlay: Remote message: {message}")

        # Add JavaScript interface
        rc_interface = RemoteControlInterface(self)
        self.webview.addJavascriptInterface(rc_interface, "RemoteControl")

        # Enable JavaScript and settings
        settings = self.webview.getSettings()
        settings.setJavaScriptEnabled(True)
        settings.setDomStorageEnabled(True)
        settings.setAllowFileAccess(True)
        settings.setAllowContentAccess(True)
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW)
        settings.setCacheMode(WebSettings.LOAD_DEFAULT)
        settings.setBuiltInZoomControls(True)
        settings.setDisplayZoomControls(False)
        settings.setSupportMultipleWindows(True)
        settings.setJavaScriptCanOpenWindowsAutomatically(True)

        # Set clients
        self.webview.setWebViewClient(EverlayWebViewClient())
        self.webview.setWebChromeClient(EverlayWebChromeClient())

        # Load the local server
        self._load_server()

        # Wrap in layout
        layout = LinearLayout(activity)
        layout.setOrientation(LinearLayout.VERTICAL)
        params = ViewGroup.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.MATCH_PARENT
        )
        layout.addView(self.webview, params)

        return layout

    def _load_server(self):
        """Load the local FastAPI server in WebView."""
        url = "http://127.0.0.1:8000"
        Logger.info(f"Everlay: Loading WebView with {url}")
        if self.webview:
            self.webview.loadUrl(url)

    def _start_server_desktop(self, instance):
        """Start server for desktop testing."""
        start_server_thread()
        instance.text = "Server Started"
        instance.disabled = True

    def on_start(self):
        """Called when app starts."""
        Logger.info("Everlay: App started, starting server...")
        start_server_thread()

        if platform == 'android':
            # Start foreground service for background operation
            self._start_foreground_service()
            # Connect to remote control WebSocket
            self._connect_remote_ws()
            # Schedule reload once server is ready
            Clock.schedule_once(self._check_server_ready, 3)

    def _connect_remote_ws(self):
        """Connect to remote control WebSocket."""
        if platform != 'android':
            return

        def run_ws():
            import asyncio
            import websockets
            import json

            async def connect():
                try:
                    # Connect to local remote control WebSocket
                    ws_url = "ws://127.0.0.1:8000/api/remote/control"
                    self._remote_ws = await websockets.connect(ws_url)
                    Logger.info("Everlay: Remote control WebSocket connected")

                    # Send welcome message
                    await self._remote_ws.send(json.dumps({
                        "type": "subscribe",
                        "events": ["file_changes", "process_changes", "system_metrics"]
                    }))

                    # Listen for messages
                    async for message in self._remote_ws:
                        data = json.loads(message)
                        # Forward to WebView JavaScript
                        if self.webview:
                            msg_json = json.dumps(data)
                            js_code = f"window.dispatchEvent(new CustomEvent('remote_message', {{detail: {msg_json}}}));"
                            # Run on UI thread
                            from android.runnable import run_on_ui_thread
                            @run_on_ui_thread
                            def exec_js():
                                self.webview.evaluateJavascript(js_code, None)
                            exec_js()

                except Exception as e:
                    Logger.error(f"Everlay: Remote WS error: {e}")

            # Run in background thread
            import threading
            threading.Thread(target=lambda: asyncio.run(connect()), daemon=True).start()

        # Run in background thread
        threading.Thread(target=run_ws, daemon=True).start()

    def _check_server_ready(self, dt):
        """Check if server is ready and reload WebView."""
        if platform == 'android' and self.webview:
            self._load_server()
            Logger.info("Everlay: WebView reloaded after server start")

    def _start_foreground_service(self):
        """Start Android foreground service to keep server alive in background."""
        try:
            # Use python-for-android's AndroidService
            from android import AndroidService
            self._foreground_service = AndroidService('Everlay Server', 'Running')
            self._foreground_service.start('Everlay AI server running in background')
            Logger.info("Everlay: Foreground service started")
        except Exception as e:
            Logger.warning(f"Everlay: Could not start foreground service: {e}")

    def on_pause(self):
        """Called when app goes to background - keep server running."""
        Logger.info("Everlay: App paused (server keeps running)")
        return True  # Keep app alive in background

    def on_resume(self):
        """Called when app returns to foreground."""
        Logger.info("Everlay: App resumed")
        if platform == 'android' and self.webview:
            self._load_server()

    def on_stop(self):
        """Called when app stops."""
        Logger.info("Everlay: App stopping")
        stop_server()

    def on_request_permissions_result(self, permissions, grant_results):
        """Handle permission results."""
        Logger.info(f"Everlay: Permissions result: {grant_results}")


# Request battery optimization exemption for background operation
@run_on_ui_thread
def request_battery_optimization_exemption():
    """Request to not optimize battery for this app."""
    try:
        if platform == 'android':
            pm = activity.getSystemService(Context.POWER_SERVICE)
            package_name = activity.getPackageName()
            if Build.VERSION.SDK_INT >= Build.VERSION_CODES.M:
                if not pm.isIgnoringBatteryOptimizations(package_name):
                    intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
                    intent.setData(autoclass('android.net.Uri').parse(f"package:{package_name}"))
                    activity.startActivity(intent)
    except Exception as e:
        Logger.warning(f"Everlay: Could not request battery exemption: {e}")


if __name__ == '__main__':
    # Setup logging
    settings = get_settings()
    setup_logging(settings)

    # Request battery optimization exemption on Android
    if platform == 'android':
        Clock.schedule_once(lambda dt: request_battery_optimization_exemption(), 2)

    # Run the app
    EverlayAndroidApp().run()