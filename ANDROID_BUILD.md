# Everlay Android Build Guide

## Quick Start

### 1. Install Buildozer (Linux/macOS/WSL)
```bash
# Ubuntu/Debian/WSL2
sudo apt update && sudo apt install -y git zip unzip openjdk-17-jdk python3-pip autoconf libtool pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev libtinfo5 cmake libffi-dev libssl-dev automake
pip install --user buildozer

# Add to PATH
export PATH=$PATH:~/.local/bin
```

### 2. Configure API Key
Edit `.env` or set environment variable before build:
```bash
export OPENROUTER_API_KEY="your-key-here"
```
Or enter it in the Web UI Settings after launching the app.

### 3. Build APK
```bash
# First build (downloads Android SDK/NDK, takes 10-30 min)
buildozer -v android debug

# Subsequent builds (faster)
buildozer android debug
```

### 4. Install on Device
```bash
# Via ADB
adb install bin/everlay-2.0.0-arm64-v8a-debug.apk

# Or copy APK to phone and install manually
```

## Build Details

### What's Included
- FastAPI server (uvicorn) running on localhost:8000
- Web UI (HTML/CSS/JS) served by FastAPI
- Native Android WebView for UI
- All agents, tools, RAG system
- SQLite database in app private storage

### Architecture
```
┌─────────────────────────────────────┐
│         Android App (Kivy)          │
│  ┌───────────────────────────────┐  │
│  │     WebView (WebKit)          │  │
│  │  http://127.0.0.1:8000        │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
              │
              ▼ (localhost)
┌─────────────────────────────────────┐
│      FastAPI Server (uvicorn)       │
│  - REST API /api/*                  │
│  - WebSocket /api/chat/stream       │
│  - Static files /static/*           │
│  - Web UI /                         │
└─────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│         Python Modules              │
│  - Agents (default, code, chat)     │
│  - Tools (file, shell, web, db...)  │
│  - RAG (SQLite + embeddings)        │
│  - OpenRouter client                │
└─────────────────────────────────────┘
```

### File Paths on Android
| File | Location |
|------|----------|
| RAG Database | `/data/user/0/org.everlay/files/everlay_brain.db` |
| Main Database | `/data/user/0/org.everlay/files/everlay.db` |
| Logs | `/data/user/0/org.everlay/files/logs/agents.log` |
| App Config | Environment variables (set in `android_main.py`) |

### Permissions
- `INTERNET` - API calls to OpenRouter
- `ACCESS_NETWORK_STATE` - Network monitoring
- `WAKE_LOCK` - Keep server alive in background
- `FOREGROUND_SERVICE` - Background operation
- `POST_NOTIFICATIONS` - Status notifications

## Troubleshooting

### Build Fails
```bash
# Clean and rebuild
buildozer android clean
buildozer -v android debug
```

### App Crashes on Start
```bash
# Check logs
adb logcat -s python:V kivy:V Everlay:V *:E
```

### Server Not Starting
- Check `adb logcat` for Python errors
- Verify `ANDROID_PRIVATE` environment variable is set
- Ensure port 8000 is not blocked

### Web UI Not Loading
- Server binds to `127.0.0.1:8000` (localhost only)
- WebView loads `http://127.0.0.1:8000`
- Check `android:usesCleartextTraffic="true"` in manifest (buildozer adds this)

## Release Build
```bash
# Create keystore (one time)
keytool -genkey -v -keystore everlay-release.keystore -alias everlay -keyalg RSA -keysize 2048 -validity 10000

# Build release
buildozer android release
# Sign with your keystore
```

## Notes
- First build downloads ~2GB (Android SDK, NDK, Python-for-Android)
- APK size: ~80-120 MB (arm64-v8a + armeabi-v7a)
- Minimum Android: API 24 (Android 7.0)
- Target Android: API 33 (Android 13)
- WebView uses system WebView (Chrome-based on Android 7+)

## Development Tips

### Test on Desktop First
```bash
# Run server
python -m api.main

# Open http://localhost:8000 in browser
```

### Debug Python Code
```bash
# Add print statements, rebuild, check logcat
adb logcat -s python:V
```

### Update Web UI
```bash
# Modify web/templates/index.html, web/static/css/main.css, web/static/js/main.js
# Rebuild APK
buildozer android debug
```