import sys
import unittest

from tests.runtime import isolated_runtime


def main() -> int:
    with isolated_runtime():
        loader = unittest.TestLoader()
        suite = (
            loader.loadTestsFromNames(names=sys.argv[1:])
            if len(sys.argv) > 1
            else loader.discover(start_dir="tests", top_level_dir=".")
        )
        result = unittest.TextTestRunner(verbosity=1).run(test=suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
