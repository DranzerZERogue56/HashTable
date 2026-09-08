[app]

title = Go
package.name = gogame
package.domain = org.hashtable

source.dir = .
source.include_exts = py
# Keep the test suite and build output out of the APK.
source.exclude_dirs = tests, gogame/tests, recipes, bin, .buildozer, .github, .git, __pycache__

version = 0.1

# python-for-android's pygame recipe is listed as broken against current
# SDL2, so the UI is Kivy, which is buildozer's default and best-supported
# path. board/rules/sgf/bot are pure stdlib and need nothing here.
requirements = python3,kivy

orientation = portrait
fullscreen = 0

# minapi 24 clears both install floors: Android 14 refuses targetSdk < 23
# and Android 15+ refuses < 24.
android.api = 36
android.minapi = 24
android.ndk_api = 24

# Every Samsung phone since ~2015 is arm64; building this one arch alone
# roughly halves build time. Add armeabi-v7a here if an older device needs it.
android.archs = arm64-v8a

android.accept_sdk_license = True
android.allow_backup = False
android.debug_artifact = apk

p4a.bootstrap = sdl2

# Local override of the kivy recipe, dropping its unused requests
# dependency chain -- see recipes/kivy/__init__.py for why.
p4a.local_recipes = ./recipes

[buildozer]

log_level = 2
warn_on_root = 0
