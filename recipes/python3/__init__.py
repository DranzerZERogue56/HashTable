"""Local override of python-for-android's python3 recipe.

Trims standard-library packages this app cannot reach out of the bundled
stdlib, which ships inside libpybundle.so (12.1 MB of the APK).

This has to happen here rather than through buildozer's
`android.blacklist_src`. That option becomes p4a's `--blacklist`, which
only filters what goes into `assets/private.tar` -- the app's own code,
all 47 KB of it. The stdlib is packed separately by
Python3Recipe.create_python_bundle(), which filters via the recipe
attributes below. Setting the buildozer blacklist instead produced an APK
that was byte-for-byte the same size.

Upstream already excludes test, tests, lib2to3, ensurepip, idlelib and
tkinter, and ships only .pyc (never .py/.whl), so those are not repeated
here -- these are the additions on top.

Deliberately NOT excluded: asyncio, which Kivy's app loop imports; the app
will not start without it. Verified by running under xvfb with each of the
modules below forced unimportable, through a full game.
"""

import importlib.util
import os

import pythonforandroid.recipes as _p4a_recipes

# p4a imports local recipes under the name "pythonforandroid.recipes.python3"
# (Recipe.get_recipe), so load the upstream module by path under a different
# name -- importing it by its real name would re-enter this file.
_UPSTREAM_DIR = os.path.join(os.path.dirname(_p4a_recipes.__file__), "python3")
_spec = importlib.util.spec_from_file_location(
    "_upstream_python3_recipe", os.path.join(_UPSTREAM_DIR, "__init__.py")
)
_upstream = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_upstream)


class Python3Recipe(_upstream.Python3Recipe):
    stdlib_dir_blacklist = {
        *_upstream.Python3Recipe.stdlib_dir_blacklist,
        "email",  # only reachable via urllib/http, and this app has no network
        "pydoc_data",  # pydoc help text
        "turtledemo",
        "unittest",
        "xml",  # no XML parsing anywhere in the app or in Kivy's startup path
    }

    def get_recipe_dir(self):
        # Recipe.get_recipe_dir() prefers the local folder once local_recipes
        # is set, which would send this recipe's many patch lookups
        # (patches/pyconfig_detection.patch, 3.14_armv7l_fix.patch, ...) here
        # instead of upstream.
        return _UPSTREAM_DIR


recipe = Python3Recipe()
