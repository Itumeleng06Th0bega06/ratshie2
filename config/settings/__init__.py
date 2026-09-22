"""Settings package.

Development default; production selected via RATSHIE_ENV=prod.
"""
import os
import sys

if os.environ.get("RATSHIE_ENV", "").lower() in ("prod", "production"):
    from .prod import *  # noqa: F401,F403
else:
    from .dev import *  # noqa: F401,F403
