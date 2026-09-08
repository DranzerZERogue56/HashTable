"""Local override of python-for-android's kivy recipe.

Upstream declares:

    python_depends = ['certifi', 'chardet', 'idna', 'requests', 'urllib3', 'filetype']

`requests` transitively pulls in charset-normalizer, which since 3.0 ships
compiled C extensions and has no p4a recipe (kivy/python-for-android#2755).
p4a cross-builds it into an android-tagged wheel, and the host pip then
refuses to install its own artifact:

    ERROR: charset_normalizer-3.5.1-cp314-cp314-android_24_arm64_v8a.whl
           is not a supported wheel on this platform

Pinning charset-normalizer in buildozer.spec does not help: the recipe's
python_depends are resolved separately and the pin just coexists with the
resolved 3.x. Every other module in that set is pure Python and installs
fine, so the fix is to drop the network chain, which this app has no use
for -- it makes no network calls at all. `filetype` is kept because Kivy's
image handling does use it.

Verified locally: the app builds its widget tree and renders with
requests, certifi, urllib3, idna, chardet and charset_normalizer all made
unimportable.
"""

import importlib.util
import os

import pythonforandroid.recipes as _p4a_recipes

# p4a imports local recipes under the name "pythonforandroid.recipes.kivy"
# (see Recipe.get_recipe), so the upstream module is loaded here by path
# under a different name -- importing it by its real name would just
# re-enter this file.
_UPSTREAM_DIR = os.path.join(os.path.dirname(_p4a_recipes.__file__), "kivy")
_spec = importlib.util.spec_from_file_location(
    "_upstream_kivy_recipe", os.path.join(_UPSTREAM_DIR, "__init__.py")
)
_upstream = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_upstream)


class KivyRecipe(_upstream.KivyRecipe):
    python_depends = ["filetype"]

    def get_recipe_dir(self):
        # Recipe.get_recipe_dir() prefers the local recipe folder once
        # local_recipes is set, which would look for the kivy .patch files
        # in this directory. Keep resolving them from upstream's.
        return _UPSTREAM_DIR


recipe = KivyRecipe()
