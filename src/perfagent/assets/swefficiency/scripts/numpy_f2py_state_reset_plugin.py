def pytest_runtest_setup(item):
    if not item.nodeid.startswith("numpy/f2py/tests/"):
        return

    from numpy.f2py import crackfortran

    crackfortran.reset_global_f2py_vars()
