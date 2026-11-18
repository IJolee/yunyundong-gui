"""网络中断后禁止继续上传或错误报告成功；全部使用模拟传输。"""
import contextlib
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import main as app


class NetworkFailureTests(unittest.TestCase):
    def test_connection_abort_is_not_retried(self):
        session = MagicMock()
        session.__enter__.return_value = session
        session.post.side_effect = app.requests.ConnectionError('WinError 10053')
        settings = dict(my_host='http://example.invalid', my_token='secret',
                        my_device_id='test', my_device_name='test', my_app_edition='3.6.6',
                        my_uuid='test', platform='android', md5key='test',
                        default_key='AAAAAAAAAAAAAAAAAAAAAA==', use_system_proxy=False)
        with patch.multiple(app, **settings), patch.object(app, 'encrypt_sm2', return_value='test'), \
                patch.object(app.requests, 'Session', return_value=session):
            with self.assertRaisesRegex(RuntimeError, '10053.*结果未知') as result:
                app.default_post('/run/splitPointCheating', '')
        self.assertNotIn('secret', str(result.exception))
        self.assertEqual(session.post.call_count, 1)

    def test_auto_run_returns_failure_without_finish_or_input(self):
        config = Path(app.__file__).parent/'config.ini'
        if not config.exists():
            config = config.with_name('config.example.ini')
        args = SimpleNamespace(config_path=str(config),
                               auto_run=True, task_path='unused', drift=False)
        runner = MagicMock()
        runner.crsRunRecordId = 123
        runner.last_confirmed_mileage = 1290.0
        runner.do_by_points_map.side_effect = RuntimeError('network failed')
        output = io.StringIO()
        with patch.object(app, 'parse_args', return_value=args), \
                patch.object(app, 'Yun_For_New', return_value=runner), \
                patch('builtins.input', side_effect=AssertionError('must not wait for input')), \
                contextlib.redirect_stdout(output):
            code = app.main()
        self.assertEqual(code, 1)
        runner.finish_by_points_map.assert_not_called()
        self.assertIn('123', output.getvalue())
        self.assertIn('1290.0', output.getvalue())


if __name__ == '__main__':
    unittest.main()
