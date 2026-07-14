# Everlay AI Environment — Project Documentation

## 📋 Project Overview

**Everlay AI Environment** — мультиплатформенная среда для работы с ИИ-агентами через OpenRouter API.
Проект предоставляет единый интерфейс для взаимодействия с языковыми моделями через:
- **Web UI** (FastAPI + HTML/JS)
- **Desktop приложение** (Tkinter/Kivy)
- **Telegram Bot** (aiogram 3)
- **Android приложение** (Kivy + WebView + Foreground Service)
- **Remote Control API** для управления ПК с телефона

---

## 🎯 Цели проекта

1. **Единая точка входа** для всех ИИ-моделей через OpenRouter
2. **Мультиплатформенность**: Windows, Linux, Android, Web
3. **Удалённое управление** ПК с телефона в реальном времени
4. **Расширяемая архитектура** агентов и инструментов
5. **Приватность**: локальное хранение данных (SQLite, RAG)

---

## ✅ Что реализовано (v2.0.0)

### 🏗 Core Infrastructure

| Компонент | Статус | Описание |
|-----------|--------|----------|
| **Config System** | ✅ | Pydantic Settings + .env, централизованные модели, пути БД |
| **OpenRouter Client** | ✅ | Async HTTP, streaming, retry logic, rate limiting, model routing |
| **Logging** | ✅ | JSON/текст, ротация файлов, уровни, структурированные логи |
| **Exceptions** | ✅ | Иерархия ошибок (Configuration, Agent, Telegram, Database) |
| **RAG System** | ✅ | SQLite + эмбеддинги (Ollama/OpenRouter/hash fallback), теги, поиск |

### 🤖 Agents System

| Агент | Инструменты | Особенности |
|-------|-------------|-------------|
| **Default** | 17 tools | Универсальный, все инструменты |
| **Code** | 11 tools | Фокус на коде, temp=0.3 |
| **Chat** | 0 tools | Чистый диалог, temp=0.8 |

**Базовые инструменты (17):**
- Файлы: read, write, list, search
- Shell: shell, python, code_interpreter
- Веб: web_search, web_scrape, http_request, json_tool
- Система: git, database, csv_tool, rag, resource_monitor, model_router

### 🌐 Web API (FastAPI)

| Endpoint | Описание |
|----------|----------|
| `GET /api/health` | Health check |
| `GET /api/agents` | Список агентов |
| `POST /api/chat` | Чат с агентом |
| `WS /api/chat/stream` | Streaming чат |
| `GET/POST/DELETE /api/sessions/*` | Управление сессиями |
| `GET /api/models` | Модели OpenRouter |
| `GET /` | Web UI (SPA) |

### 📱 Telegram Bot (aiogram 3)

| Команда | Описание |
|---------|----------|
| `/start`, `/help` | Старт и справка |
| `/agent`, `/agents` | Смена/список агентов |
| `/model`, `/status`, `/clear` | Настройки сессии |
| **Build команды:** | |
| `/build` | Инфо + **inline-кнопки** скачивания/сборки |
| `/apk` | Отправка Android APK |
| `/apkwindows` | Отправка Windows EXE |
| `/build_status` | Статус GitHub Actions |

**Inline-кнопки в `/build`:**
- 📱 Download Android APK
- 💻 Download Windows EXE
- 🔨 Build APK (Linux/WSL)
- 🔨 Build EXE (Windows)
- 📊 Build Status

### 🖥 Desktop GUI (Tkinter)

- Тёмная тема, синтаксис-подсветка
- Выбор агента/модели
- Streaming ответы
- История чата с копированием

### 📱 Android App (Kivy + WebView)

| Функция | Реализация |
|---------|------------|
| **WebView** | Загружает `http://127.0.0.1:8000` |
| **Foreground Service** | Работа в фоне, уведомление в трее |
| **Remote Control WS** | Подключение к `ws://127.0.0.1:8000/api/remote/control` |
| **JavaScript Interface** | `RemoteControl` bridge для WebView↔Python |
| **Battery Optimization Exemption** | Запрос на исключение из оптимизации |

### 🎮 Remote Control System (NEW)

| Модуль | Инструменты | WebSocket Events |
|--------|-------------|------------------|
| **File Manager** | list, read, write, delete, copy, move, search, upload/download (base64) | `execute`, `result` |
| **Process Manager** | list, kill, start, info, cpu/memory, tree | `execute`, `result` |
| **System Control** | shutdown/restart/sleep/lock, clipboard, notify, volume, brightness, screenshot, WiFi | `execute`, `result` |
| **Monitoring** | CPU, RAM, диск, сеть каждые 2 сек | `metrics`, `system_info` |

**Endpoints:**
- `WS /api/remote/control` — управление (execute, subscribe)
- `WS /api/remote/events` — метрики системы
- `POST /api/remote/execute` — REST execute
- `GET /api/remote/status` — статус сервера
- `GET /api/remote/tools` — список инструментов

### 🔧 Build System

| Скрипт | Назначение |
|--------|------------|
| `build_exe.py` | PyInstaller → `dist/Everlay/Everlay.exe` (22 MB) |
| `buildozer.spec` | Android APK (arm64-v8a, armeabi-v7a) |
| `remote_service.py` | Android Foreground Service |
| `ANDROID_BUILD.md` | Инструкция по сборке |

### 📦 Dependencies

**Python packages:**
```
Core: pydantic, pydantic-settings, python-dotenv, asyncio
Web: fastapi, uvicorn[standard], httpx, aiohttp
DB: sqlalchemy, aiosqlite, redis
Bot: aiogram>=3.10
Parsing: beautifulsoup4, lxml
Remote: psutil, pyautogui, pyperclip, Pillow, pycaw, comtypes, win10toast
Build: pyinstaller, buildozer, cython
Test: pytest, pytest-asyncio
```

### 📁 Project Structure

```
Project_Everlay_2.0/
├── api/
│   └── main.py              # FastAPI + Remote Control WS
├── agents/
│   ├── base.py              # BaseAgent, Tool, Context, Result
│   ├── tools.py             # 17 builtin tools
│   ├── remote_tools.py      # 4 remote tools (NEW)
│   ├── presets.py           # DefaultAgent, CodeAgent, ChatAgent
│   └── __init__.py
├── core/
│   ├── config.py            # Pydantic Settings
│   ├── openrouter_client.py # Async OpenRouter client
│   ├── exceptions.py        # Exception hierarchy
│   ├── logging_config.py    # Logging setup
│   └── rag.py               # RAG system
├── telegram/
│   └── bot.py               # Telegram bot with inline buttons
├── web/
│   ├── templates/index.html # SPA Web UI
│   └── static/css/, js/     # Styles & scripts
├── tests/
│   ├── test_config.py
│   ├── test_csv_tool.py
│   └── test_rag.py
├── android_main.py          # Kivy Android entry point
├── remote_service.py        # Android Foreground Service (NEW)
├── run_bot.py               # Telegram bot entry
├── run_desktop.py           # Tkinter desktop entry
├── build_exe.py             # PyInstaller build script
├── buildozer.spec           # Android APK config
├── remote_service.py        # Android Foreground Service
├── requirements.txt
├── ANDROID_BUILD.md
├── .env.example
└── .env
```

---

## 🚀 Что будет добавлено (Roadmap)

### v2.1 — Remote Control Enhancement
- [ ] **File Transfer** — drag&drop через Web UI
- [ ] **Terminal Emulator** — полноценный shell в браузере
- [ ] **Remote Desktop** — VNC/RDP через WebRTC
- [ ] **Voice Commands** — управление голосом через телефон
- [ ] **Clipboard Sync** — двусторонний буфер обмена

### v2.2 — Mobile App Improvements
- [ ] **Native UI** — частичный переход на нативные экраны
- [ ] **Offline Mode** — кэширование чатов
- [ ] **Push Notifications** — FCM для Telegram/алертов
- [ ] **Biometric Auth** — отпечаток/лицо для доступа
- [ ] **Widget** — быстрый доступ к чату

### v2.3 — AI Enhancements
- [ ] **Multi-Agent Orchestration** — цепочки агентов
- [ ] **Custom Tools SDK** — Python SDK для своих инструментов
- [ ] **RAG v2** — векторная БД (Chroma/Qdrant), hybrid search
- [ ] **Fine-tuning Pipeline** — дообучение моделей
- [ ] **Prompt Library** — шаблоны промптов

### v2.4 — Enterprise Features
- [ ] **Multi-user** — роли, права, организации
- [ ] **Audit Log** — логи всех действий
- [ ] **SSO/OAuth** — Google, GitHub, Microsoft
- [ ] **API Keys Management** — управление ключами OpenRouter
- [ ] **Usage Analytics** — токены, стоимость, лимиты

---

## 💡 Идеи для будущего (Backlog)

### 🔧 Technical Improvements
| Идея | Описание | Сложность |
|------|----------|-----------|
| **Plugin System** | Горячая загрузка инструментов/агентов | Высокая |
| **Distributed Agents** | Агенты на разных машинах | Высокая |
| **GraphQL API** | Альтернатива REST | Средняя |
| **gRPC Support** | Высокопроизводительный RPC | Высокая |
| **Edge Deployment** | Запуск на Raspberry Pi/Edge | Средняя |

### 🤖 AI Features
| Идея | Описание | Сложность |
|------|----------|-----------|
| **Auto-GPT Mode** | Автономные агенты с целями | Высокая |
| **Code Interpreter Sandbox** | Изолированное выполнение кода | Высокая |
| **Multi-modal Support** | Изображения, аудио, видео | Высокая |
| **Local LLM Support** | llama.cpp, Ollama, vLLM | Средняя |
| **Agent Marketplace** | Обмен агентами/промптами | Средняя |

### 📱 Mobile & Desktop
| Идея | Описание | Сложность |
|------|----------|-----------|
| **iOS App** | SwiftUI + WebKit | Высокая |
| **macOS App** | Native + Catalyst | Средняя |
| **Linux Tray App** | AppIndicator + DBus | Низкая |
| **VS Code Extension** | Интеграция с редактором | Средняя |
| **Raycast/Alfred Plugin** | Быстрый доступ | Низкая |

### 🌐 Integrations
| Идея | Описание | Сложность |
|------|----------|-----------|
| **GitHub/GitLab Bot** | PR review, issue triage | Средняя |
| **Jira/Linear Bot** | Task management | Средняя |
| **Slack/Discord Bot** | Team collaboration | Низкая |
| **Notion/Obsidian Sync** | Knowledge base | Средняя |
| **Zapier/Make Webhooks** | No-code automation | Низкая |

---

## 📊 Metrics & KPIs

| Метрика | Текущее | Цель v2.1 |
|---------|---------|-----------|
| **Test Coverage** | 15 tests pass | >80% |
| **Build Time (APK)** | ~20 min | <10 min |
| **Build Time (EXE)** | ~3 min | <1 min |
| **APK Size** | ~80 MB | <50 MB |
| **EXE Size** | 22 MB | <15 MB |
| **Cold Start (Android)** | ~5 сек | <3 сек |
| **WS Latency** | <50 ms | <20 ms |
| **Remote Command Latency** | <200 ms | <100 ms |

---

## 🛠 Development Setup

```bash
# Windows
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# Run services
python -m api.main          # Web API :8000
python run_desktop.py       # Desktop GUI
python run_bot.py           # Telegram Bot

# Build
python build_exe.py         # Windows EXE

# Android (WSL2/Linux)
buildozer -v android debug
```

---

## 📝 Deployment Checklist

- [ ] `.env` с `OPENROUTER_API_KEY`, `TELEGRAM_BOT_TOKEN`
- [ ] `WEB_CORS_ORIGINS` для продакшена
- [ ] `WEB_SECRET_KEY` — случайная строка
- [ ] SSL сертификаты для HTTPS
- [ ] Reverse proxy (nginx) для FastAPI
- [ ] Systemd service для бота и API
- [ ] GitHub Secrets для CI/CD
- [ ] Keystore для подписи APK

---

## 📞 Contacts & Links

- **Repository**: [GitHub](https://github.com/your-repo/everlay)
- **Issues**: [GitHub Issues](https://github.com/your-repo/everlay/issues)
- **Wiki**: [Project Wiki](https://github.com/your-repo/everlay/wiki)
- **Telegram**: @everlay_system_bot

---

## 📄 License

MIT License — свободное использование, модификация, распространение.

---

*Документ создан: 2024-07-13*
*Версия проекта: 2.0.0*
*Автор: Everlay Team*