[app]

# (str) Title of your application
title = Everlay AI

# (str) Package name
package.name = everlay

# (str) Package domain (needed for android/ios packaging)
package.domain = org.everlay

# (str) Source code where the main.py live
source.dir = .

# (list) Source files to include (let buildozer find them)
source.include_exts = py,png,jpg,kv,atlas,html,css,js,json,db,ico

# (list) List of inclusions using pattern matching
source.include_patterns = assets/*,web/*,core/*,agents/*,telegram/*,api/*,requirements.txt,.env.example

# (list) Source files to exclude (let buildozer ignore them)
source.exclude_exts = spec

# (list) List of directory to exclude (let buildozer ignore them)
source.exclude_dirs = tests,build,dist,__pycache__,.git,.claude,logs,venv,.venv,env,*.egg-info

# (list) List of exclusions using pattern matching
source.exclude_patterns = *.pyc,*.pyo,*.pyd,*.so,*.dll,*.exe,*.bat,*.cmd,*.sh,*.md,*.txt,*.rst,*.spec,*.ico

# (str) Application versioning (method 1)
version = 2.0.0

# (str) Application versioning (method 2)
# version.regex = __version__ = ['"](.*)['"]
# version.filename = %(source.dir)s/%(package.name)s/__init__.py

# (list) Application requirements
# comma separated e.g. requirements = sqlite3,kivy
requirements = python3,kivy,fastapi,uvicorn[standard],httpx,pydantic,pydantic-settings,python-dotenv,aiosqlite,sqlalchemy,redis,beautifulsoup4,lxml,numpy,aiohttp,aiogram,pillow,psutil,python-for-android,pyperclip

# (str) Custom source folders for requirements
# requirements.source =

# (list) Garden requirements
# garden_requirements =

# (str) Presplash of the application
presplash.filename = %(source.dir)s/assets/presplash.png

# (str) Icon of the application
icon.filename = %(source.dir)s/assets/icon.ico

# (str) Supported orientation (one of landscape, sensorLandscape, portrait or all)
orientation = portrait

# (list) List of service to declare
services = EVERLAY_REMOTE:remote_service.py

# (str) Additional permissions
android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,WAKE_LOCK,FOREGROUND_SERVICE,FOREGROUND_SERVICE_DATA_SYNC,FOREGROUND_SERVICE_MEDIA_PROJECTION,POST_NOTIFICATIONS,VIBRATE,RECEIVE_BOOT_COMPLETED,CAMERA,RECORD_AUDIO,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,MANAGE_EXTERNAL_STORAGE,SYSTEM_ALERT_WINDOW,BLUETOOTH,BLUETOOTH_ADMIN,BLUETOOTH_CONNECT,BLUETOOTH_SCAN,BLUETOOTH_ADVERTISE,USE_FULL_SCREEN_INTENT

# (list) List of features
# android.features =

# (int) Android API to use
android.api = 34

# (int) Minimum Android API required
android.minapi = 24

# (int) Android SDK version to use
android.sdk = 34

# (str) Android NDK version to use
android.ndk = 27c

# (int) Android NDK API to use
android.ndk_api = 24

# (bool) Use --private data storage (True) or public (False)
android.private_storage = True

# (str) Android entry point (default is ok for kivy)
android.entrypoint = org.kivy.android.PythonActivity

# (list) Android additional libraries to copy into libs/armeabi
# android.add_libs_armeabi = libs/android/*.so

# (list) Android additional libraries to copy into libs/armeabi-v7a
# android.add_libs_armeabi_v7a = libs/android7/*.so

# (list) Android additional libraries to copy into libs/arm64-v8a
# android.add_libs_arm64_v8a = libs/android64/*.so

# (list) Android additional libraries to copy into libs/x86
# android.add_libs_x86 = libs/android86/*.so

# (list) Android additional libraries to copy into libs/x86_64
# android.add_libs_x86_64 = libs/android64/*.so

# (bool) Enable AndroidX (required for API 33+)
android.enable_androidx = True

# (bool) If True, skip building the APK (useful for testing buildozer)
# android.skip_build = False

# (str) Python-for-android branch to use
p4a.branch = master

# (str) Python-for-android git clone url
p4a.git = https://github.com/kivy/python-for-android.git

# (bool) If True, then skip trying to update the Android SDK
# android.skip_update = False

# (str) Android arch to build for
android.archs = arm64-v8a,armeabi-v7a

# (int) Number of parallel jobs for building
# p4a.num_jobs = 4

# (str) Command to run after building the APK
# android.post_build =

# (bool) If True, then use the new gradle build system (default)
android.gradle = True

# (str) Gradle version to use
android.gradle_version = 8.5

# (list) Additional gradle dependencies
android.gradle_dependencies = androidx.appcompat:appcompat:1.7.0,androidx.webkit:webkit:1.12.0,com.google.android.material:material:1.12.0,androidx.lifecycle:lifecycle-process:2.8.0,androidx.work:work-runtime:2.9.0

# (str) Extra arguments to pass to gradle
# android.gradle_extra_args =

# (bool) If True, copy the icon to the mipmap folders
android.icon.copy = True

# (bool) If True, the splash screen will be displayed
android.splash = True

# (str) Splash screen color
android.splash_color = #1e1e1e

# (int) Timeout for starting the app in seconds
android.startup_timeout = 60

# (list) Permissions to add to the manifest
# android.permissions =

# (str) Python-for-android bootstraps to use
# p4a.bootstrap = sdl2

# (str) Entry point for the application (default: main.py)
main.python = android_main.py

# (list) Additional files to copy to the APK
# android.copy_libs =

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug)
log_level = 2

# (bool) Display warning if buildozer is run as root
warn_on_root = True

# (str) Path to build artifact storage
# build_dir = ./.buildozer

# (str) Path to build output (where .apk, .ipa, etc. go)
# bin_dir = ./bin

# (bool) If True, buildozer will automatically sign the APK
# android.sign = False

# (str) Keystore file for signing
# android.keystore =

# (str) Keystore password
# android.keystore_password =

# (str) Key alias
# android.key_alias =

# (str) Key password
# android.key_password =

# (str) PyPI server for requirements
# pypi.url = https://pypi.org/simple

# (str) Cache directory for p4a
# p4a.cache_dir =

# (bool) If True, buildozer will use the system's virtualenv
# buildozer.venv = False