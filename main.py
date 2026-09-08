"""Android entry point.

buildozer requires a main.py at the root of source.dir, and Android
starts the app with no command line, so this just launches the UI with
its defaults (or whatever game was autosaved). The desktop CLI with its
--size/--komi/--handicap/--sgf flags lives in gogame/main.py.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gogame.app import GoApp  # noqa: E402  (must follow the sys.path setup)

if __name__ == "__main__":
    GoApp().run()
