"""
pipeline3 package init.

Every module in this package uses flat, sibling-style imports (`import db`,
`import tools`, `import handlers`, ...) rather than relative package imports,
so pipeline3/app.py keeps working when run standalone as a script
(`cd pipeline3 && python app.py`).

Importing this package from outside instead (e.g. `from pipeline3 import
router` in the repo-root main.py, for the unified backend) needs pipeline3's
own directory on sys.path for those flat imports to resolve - added here,
once, before any submodule loads.
"""

import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))
