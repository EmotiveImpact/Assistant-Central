import bootstrap
import unittest
if __name__ == '__main__':
    suite = unittest.defaultTestLoader.discover(str(bootstrap.ROOT / 'raw_tests'))
    raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
