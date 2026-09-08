[app]

title = Go
package.name = gogame
package.domain = org.hashtable

source.dir = .
source.include_exts = py
# Keep the test suite and build output out of the APK.
source.exclude_dirs = tests, gogame/tests, bin, .buildozer, .github, .git, __pycache__

version = 0.1

# python-for-android's pygame recipe is listed as broken against current
# SDL2, so the UI is Kivy, which is buildozer's default and best-supported
# path. board/rules/sgf/bot are pure stdlib and need nothing here.
#
# charset-normalizer is pinned to the last pure-Python line on purpose.
# p4a's kivy recipe declares python_depends on requests, which pulls
# charset-normalizer; since 3.0 that ships compiled C extensions
# (p4a issue #2755), and the android-tagged wheel p4a builds is then
# rejected by the host pip with "not a supported wheel on this platform".
# 2.x is py3-none-any, satisfies requests' >=2,<4, and installs cleanly.
requirements = python3,kivy,charset-normalizer==2.1.1

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

[buildozer]

log_level = 2
warn_on_root = 0
