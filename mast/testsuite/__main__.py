import os
import sys
import unittest
from mast.cli import Cli
from mast.logging import make_logger

__version__ = "{}-0".format(os.environ["MAST_VERSION"])
here = os.path.dirname(__file__)

unittest_dir = os.path.join(here, "unit")
unittest_suite = unittest.defaultTestLoader.discover(
    start_dir=unittest_dir,
    top_level_dir=unittest_dir)

integration_dir = os.path.join(here, "integration")
integration_suite = unittest.defaultTestLoader.discover(
    start_dir=integration_dir,
    top_level_dir=integration_dir)

regression_dir = os.path.join(here, "regression")
regression_suite = unittest.defaultTestLoader.discover(
    start_dir=regression_dir,
    top_level_dir=regression_dir)

def main(out_file="stdout",
         unit=False,
         integration=False,
         regression=False,
         All=False,
         version=False):
    """
    mast.testsuite

    A testsuite for MAST for IBM DataPower. This module is executable
    from mast, the following options can be specified:

    * `-u, --unit`: If specified, run the unit tests
    * `-i, --integration`: If specified, run the integration tests
    * `-r, --regression`: If specified, run the regression tests
    * `-o, --out-file`: If given, the path and filename of where you
    would like the results written. Defaults to `stdout`. Will overwrite
    given file
    * `-h, --help`: Print this help message and exit
    * `-v, --version`: Print version number and exit
    """
    if version:
        print "mast.testsuite - version {}".format(__version__)
        sys.exit(0)
    suites = []
    if unit:
        suites.append(unittest_suite)
    if integration:
        suites.append(integration_suite)
    if regression:
        suites.append(regression_suite)
    if All:
        suites = [unittest_suite, integration_suite, regression_suite]

    suite = unittest.TestSuite(suites)
    if out_file is "stdout":
        unittest.TextTestRunner(stream=sys.stdout, verbosity=0).run(suite)
    else:
        with open(out_file, "w") as fp_out:
            unittest.TextTestRunner(stream=fp_out, verbosity=0).run(suite)


if __name__ == "__main__":
    cli = Cli(main=main, description=main.__doc__)
    try:
        cli.run()
    except SystemExit:
        pass
    except:
        make_logger("error").exception("An unhandled exception occurred during execution")
        raise
