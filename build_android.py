#!/usr/bin/env python3
"""
Build script for Everlay Android APK using Buildozer.
Run this from the project root directory.
"""
import os
import sys
import subprocess
import shutil
from pathlib import Path


def run_cmd(cmd, cwd=None, env=None):
    """Run command and return result."""
    print(f"Running: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    result = subprocess.run(cmd, cwd=cwd, env=env, shell=isinstance(cmd, str))
    if result.returncode != 0:
        print(f"Command failed with code {result.returncode}")
    return result


def main():
    project_root = Path(__file__).parent
    os.chdir(project_root)

    print("=" * 60)
    print("Everlay Android APK Build")
    print("=" * 60)

    # Check buildozer
    if not shutil.which("buildozer"):
        print("Buildozer not found. Install with: pip install buildozer")
        print("On Linux, you also need: sudo apt install -y git zip unzip openjdk-17-jdk python3-pip autoconf libtool pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev libtinfo5 cmake libffi-dev libssl-dev automake")
        sys.exit(1)

    # Clean previous builds if requested
    if "--clean" in sys.argv:
        print("Cleaning previous builds...")
        for d in [".buildozer", "bin", "build"]:
            p = project_root / d
            if p.exists():
                shutil.rmtree(p)
                print(f"  Removed {d}")

    # Build APK
    print("\nBuilding APK...")
    print("This may take 10-30 minutes on first run (downloads Android SDK/NDK)...")

    # Use debug build by default, --release for release
    build_type = "debug" if "--release" not in sys.argv else "release"

    cmd = ["buildozer", "-v", "android", build_type]

    # Add keystore args if release
    if build_type == "release":
        keystore = os.environ.get("ANDROID_KEYSTORE")
        if not keystore:
            print("ERROR: Release build requires ANDROID_KEYSTORE environment variable")
            sys.exit(1)

    result = run_cmd(cmd)

    if result.returncode == 0:
        print("\n" + "=" * 60)
        print("BUILD SUCCESSFUL!")
        print("=" * 60)

        # Find APK
        bin_dir = project_root / "bin"
        apks = list(bin_dir.glob("*.apk"))
        if apks:
            for apk in apks:
                size_mb = apk.stat().st_size / (1024 * 1024)
                print(f"APK: {apk} ({size_mb:.1f} MB)")
        else:
            print("APK not found in bin/")
    else:
        print("\n" + "=" * 60)
        print("BUILD FAILED!")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()