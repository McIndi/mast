from system import cli

# Fix issue with __main__.py messing up command line help
import sys
sys.argv[0] = "mast-system"

try:
    cli.Run()
except AttributeError, e:
    if "'NoneType' object has no attribute 'app'" in e:
        raise NotImplementedError(
            "HTML formatted output is not supported on the CLI")
    raise
