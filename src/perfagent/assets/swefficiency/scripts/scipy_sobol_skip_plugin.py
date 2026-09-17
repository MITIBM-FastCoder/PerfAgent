"""Skip Sobol-dependent tests when the bundled Sobol direction numbers are absent.

Some scipy test images are missing `_sobol_direction_numbers.npz` next to the
compiled `_sobol` extension. Accessing Sobol in that state raises a
FileNotFoundError and later trips pytest's unraisable-exception machinery,
which can surface as unrelated setup errors in subsequent tests.

Patch the Python-level Sobol entrypoints rather than only the low-level Cython
helper. In this SciPy build, rebinding `_sobol._initialize_v` alone is not
enough because the compiled path still reaches the original implementation.
"""

from __future__ import annotations

from pathlib import Path
import unittest


def pytest_configure(config):
    try:
        import scipy.stats._sobol as _sobol
    except Exception:
        return

    sobol_data = Path(_sobol.__file__).resolve().with_name("_sobol_direction_numbers.npz")
    if sobol_data.exists():
        return

    def _raise_skip(*args, **kwargs):
        raise unittest.SkipTest(
            f"Skipping because Sobol data file is missing: {sobol_data}"
        )

    # Keep the low-level patch as a fallback for any direct Python-level calls.
    _sobol._initialize_v = _raise_skip

    try:
        import scipy.stats._qmc as _qmc
    except Exception:
        _qmc = None

    if _qmc is not None and hasattr(_qmc, "Sobol"):
        original_sobol = _qmc.Sobol

        class _MissingSobolDataSobol(original_sobol):
            def __init__(self, *args, **kwargs):
                _raise_skip()

        _MissingSobolDataSobol.__name__ = original_sobol.__name__
        _MissingSobolDataSobol.__qualname__ = original_sobol.__qualname__
        _MissingSobolDataSobol.__module__ = original_sobol.__module__
        _qmc.Sobol = _MissingSobolDataSobol

        try:
            import scipy.stats.qmc as qmc
        except Exception:
            qmc = None
        if qmc is not None:
            qmc.Sobol = _MissingSobolDataSobol
