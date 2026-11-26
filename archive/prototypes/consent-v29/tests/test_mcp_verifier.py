"""MCP is optional at runtime, mandatory for complete checkpoint evidence."""
import unittest
import verify_checkpoint as verifier
import test_verify_checkpoint as baseline


class MCPVerifierTests(unittest.TestCase):
    invoke = baseline.ReportTests.invoke

    def test_probe_imports_client_and_server_and_checks_version(self):
        self.assertEqual(verifier.PINS['mcp'], '1.29.0')
        self.assertIn('from mcp import ClientSession', verifier.DEPENDENCY_PROBE)
        self.assertIn('from mcp.server.lowlevel import Server', verifier.DEPENDENCY_PROBE)
        self.assertIn("'mcp'", verifier.DEPENDENCY_PROBE)

    def test_missing_sdk_version_does_not_pass_or_run_python(self):
        versions = {k:v for k,v in verifier.PINS.items() if k != 'mcp'}
        result = self.invoke(full=True, versions=versions)
        self.assertEqual(result['status'], 'incomplete-or-failed')
        self.assertEqual(result['checks']['python_dependencies']['status'], 'failed')
        self.assertEqual(result['suites']['python']['status'], 'not-run')
        self.assertIn('MCP SDK', result['suites']['python']['reason'])
        self.assertFalse(any('unittest' in c for c in self.calls))

    def test_wrong_sdk_version_does_not_run_python(self):
        result = self.invoke(full=True, versions={**verifier.PINS, 'mcp':'1.28.1'})
        self.assertEqual(result['suites']['python']['status'], 'not-run')
        self.assertEqual(result['status'], 'incomplete-or-failed')

    def test_failed_sdk_import_does_not_skip_as_success(self):
        result = self.invoke(full=True, dependency_status='failed',
                             probe_output='ModuleNotFoundError: No module named mcp')
        self.assertEqual(result['suites']['python']['status'], 'not-run')
        self.assertEqual(result['status'], 'incomplete-or-failed')
        self.assertTrue(all(result['suites'][n]['status'] == 'passed' for n in verifier.DOM_SUITES))
