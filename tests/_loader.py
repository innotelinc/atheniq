"""Load AthenIQ's hyphenated, non-package scripts as importable modules.

The operator scripts are standalone (`scripts/foo-bar.py`), not a package, so
the tests load them by path with importlib. Importing them runs only their
module-level definitions — the `if __name__ == "__main__"` guard keeps main()
out of the way.
"""
import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def load(script_name):
    path = SCRIPTS / script_name
    module_name = pathlib.Path(script_name).stem.replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
