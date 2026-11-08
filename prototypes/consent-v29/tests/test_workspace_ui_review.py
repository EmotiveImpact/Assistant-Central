"""Independent v17 review: in-process HTTP only, not browser acceptance."""
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlencode

# Import helpers through module, never imported TestCase classes (no duplicates).
import test_workspace_ui as support
from network import Denied
from workspace_ui_service import WorkspaceUIService


class WorkspaceUIIndependentReviewTests(unittest.TestCase):
    def test_all_nonfinite_encodings_rejected_before_service_dispatch(self):
        service = Mock()
        service.action.return_value = {}
        for handler in (support.Handler, support.WorkspaceHandler):
            http = support.InProcessHTTP(service, handler)
            for number in ('NaN', 'Infinity', '-Infinity', '1e9999', '-1e9999'):
                for body in ('{"x":' + number + '}', '{"request":{"x":[' + number + ']}}'):
                    with self.subTest(handler=handler.__name__, body=body):
                        self.assertEqual(http.call('POST', '/api/action', body)[0], 400)
        service.action.assert_not_called()

    def test_finite_json_numbers_keep_standard_parser_behavior_in_both_modes(self):
        for handler in (support.Handler, support.WorkspaceHandler):
            service = Mock()
            service.action.return_value = {}
            http = support.InProcessHTTP(service, handler)
            self.assertEqual(http.call('POST','/api/action','{"x":[1.25,-2e3,1e-9999]}')[0],200)
            service.action.assert_called_once_with({'x':[1.25,-2000.0,0.0]})

    def test_invalid_utf8_nested_duplicates_and_integer_limit_fail_closed(self):
        service = Mock()
        http = support.InProcessHTTP(service)
        bodies = [b'{"x":"\xff"}', '{"request":{"owner":"alice","owner":"bob"}}',
                  '{"x":' + '9' * 5000 + '}']
        for body in bodies:
            with self.subTest(size=len(body)):
                self.assertEqual(http.call('POST', '/api/action', body)[0], 400)
        service.action.assert_not_called()

    def test_deep_json_array_cannot_create_workspace_service(self):
        ui = WorkspaceUIService()
        self.addCleanup(ui.close)
        http = support.InProcessHTTP(ui)
        self.assertEqual(http.call('POST', '/api/action', '[' * 2000 + '0' + ']' * 2000)[0], 400)
        self.assertEqual(ui.workspace._slots,{})

    def test_encoded_duplicate_queries_never_route(self):
        service = Mock()
        http = support.InProcessHTTP(service)
        query = urlencode({'selector':'garden','context':'a'*64,'owner':'alice'})
        for suffix in ('&%6fwner=bob', '&%63ontext=other', '&selector=', '&owner', '&&x=1'):
            with self.subTest(suffix=suffix):
                self.assertNotEqual(http.call('GET','/api/state?' + query + suffix)[0],200)
        service.state.assert_not_called()

    def test_reads_enforce_origin_and_fetch_site_before_dispatch(self):
        service = Mock()
        http = support.InProcessHTTP(service)
        for headers in ([('Origin','null')], [('Origin',http.server.origin),('Origin',http.server.origin)],
                        [('Sec-Fetch-Site','cross-site')]):
            self.assertEqual(http.call('GET','/api/tasks',headers=headers)[0],400)
        service.tasks.assert_not_called()

    def test_exact_context_is_checked_before_every_workspace_operation(self):
        ui = WorkspaceUIService()
        self.addCleanup(ui.close)
        rows = {r['selector']:r for r in ui.tasks()}
        wrong = rows['astronomy']['context']
        with patch('owner_workspace.OwnerUIService') as factory:
            calls = [lambda:ui.state('garden',wrong,'alice'),
                     lambda:ui.review('garden',wrong,'alice','r'),
                     lambda:ui.delivery('garden',wrong,'alice','r'),
                     lambda:ui.proposals('garden',wrong,'alice')]
            for request in ({'action':'create'}, {'action':'next'},
                            {'action':'import_proposal','owner':'alice','proposal_id':'p'},
                            {'action':'close','confirmation':'DISCARD FIXTURE'}):
                calls.append(lambda request=request:ui.action({'selector':'garden','context':wrong,'request':request}))
            for call in calls:
                with self.assertRaises(Denied):call()
            factory.assert_not_called()
        self.assertEqual(ui.workspace._slots,{})

    def test_import_adapter_preserves_actual_card_shape_without_extra_wrapping(self):
        ui = WorkspaceUIService()
        self.addCleanup(ui.close)
        context = ui.tasks()[0]['context']
        card = {'owner':'alice','request_id':'exact-request','state':'declined'}
        with patch.object(ui.workspace,'import_proposal',return_value=card) as imported:
            result = ui.action({'selector':'garden','context':context,'request':
                                {'action':'import_proposal','owner':'alice','proposal_id':'exact-proposal'}})
        self.assertEqual(result,{'kind':'request','card':card})
        self.assertIs(result['card'],card)
        imported.assert_called_once_with('garden',context,'alice','exact-proposal')

    def test_task_close_never_returns_legacy_launcher_shutdown_flag(self):
        ui = WorkspaceUIService()
        self.addCleanup(ui.close)
        context = ui.tasks()[0]['context']
        with patch.object(ui.workspace,'action',return_value={'closed':True}):
            result = ui.action({'selector':'garden','context':context,'request':
                                {'action':'close','confirmation':'DISCARD FIXTURE'}})
        self.assertEqual(result,{'task_closed':True,'selector':'garden','context':context})
        self.assertNotIn('closed',result)


if __name__ == '__main__':unittest.main()
