"""Astropy stable-suite bootstrap tweaks.

This module is imported automatically by Python when present on PYTHONPATH as
`sitecustomize`. We use it in offline astropy test images to prevent stale
IERS/leap-second metadata from turning into hard failures during suite
generation.
"""

import os
import sys
from pathlib import Path


if os.environ.get("ASTROPY_LEGACY_GET_MARKER_SHIM") == "1":
    try:
        from _pytest.nodes import Node
    except Exception:
        pass
    else:
        if not hasattr(Node, "get_marker") and hasattr(Node, "get_closest_marker"):
            Node.get_marker = Node.get_closest_marker


testbed = Path("/testbed")
if testbed.is_dir():
    testbed_str = str(testbed)
    if testbed_str not in sys.path:
        sys.path.insert(0, testbed_str)

try:
    from astropy.utils import iers
except Exception:
    # Some older images import sitecustomize before astropy is importable.
    # Fail open rather than aborting the entire pytest process.
    pass
else:
    # Stable-suite runs execute without internet access, so auto-refresh
    # attempts cannot succeed. Allow the bundled leap-second file even if its
    # metadata is past the nominal refresh window.
    iers.conf.auto_download = False
    iers.conf.auto_max_age = None
