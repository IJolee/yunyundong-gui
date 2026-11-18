"""窗口组件和预览状态测试，使用临时目录，不联网、不操作用户窗口。"""
import json
from pathlib import Path
import shutil
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

from build_public_release import demo_route
from desktop_core import Library, ROOT


class DesktopWindowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        shutil.copyfile(ROOT/'config.example.ini', self.folder/'config.example.ini')
        (self.folder/'tasks_else').mkdir()
        (self.folder/'tasks_else/tasklist_demo.json').write_text(json.dumps(demo_route(150, 4)), encoding='utf-8')
        self.lib = Library(self.folder)
        self.config = self.lib.save_profile({'username': 'demo_test', 'school_host': 'http://127.0.0.1:8088/m-api',
                                             'token': '', 'password': '', 'app_edition': '3.6.7'})
        from desktop import Desktop
        try:
            self.app = Desktop(self.folder)
        except tk.TclError as exc:
            self.skipTest(f'没有 Tk 图形环境：{exc}')
        self.app.withdraw()
        self.addCleanup(self.app.destroy)

    def test_generate_preview_invalidated_by_parameter_change(self):
        app = self.app
        with patch('socket.socket', side_effect=AssertionError('network forbidden')), \
                patch('desktop.messagebox.showerror') as error:
            app.generate()
            error.assert_not_called()
        self.assertIsNotNone(app.current_fixture)
        self.assertEqual(app.fixture_config, self.config)
        self.assertGreater(len(app.canvas.find_all()), 0)
        self.assertGreater(len(app.chart.find_all()), 0)
        self.assertEqual(len(app.tabs.tabs()), 6)
        app.params['distance_km'].set('1.5')
        self.assertIsNone(app.current_fixture)
        self.assertIsNone(app.fixture_hash)

    def test_walk_mode_and_submit_guard(self):
        app = self.app
        app.params['mode'].set('walk')
        app.change_mode()
        self.assertEqual(app.params['cadence'].get(), '120')
        self.assertEqual(app.params['variation'].get(), '5')
        with patch('desktop.messagebox.showerror') as error, patch.object(app, 'start_job') as start:
            app.upload_preview()
            error.assert_called_once()
            start.assert_not_called()
        with patch('desktop.messagebox.showerror') as error:
            app.generate()
            error.assert_not_called()
        d = json.loads(app.current_fixture.read_text(encoding='utf-8'))['data']
        self.assertEqual((d['duration'], d['recodePace'], d['recodeCadence']), (1080, 9, 120))

    def test_parallel_jobs_keep_callbacks_logs_and_stop_isolated(self):
        from unittest.mock import Mock
        app = self.app
        other = self.lib.save_profile({'username': 'other', 'school_host': 'http://127.0.0.1:8088/m-api'})
        first, second = Mock(), Mock()
        first.poll.return_value = None
        second.poll.return_value = None
        callback_a, callback_b = Mock(), Mock()
        a = app.register_job(first, self.config, 'upload', callback_a, True)
        with self.assertRaises(ValueError):
            app.check_available(self.config)
        app.refresh_profiles(other)
        app.check_available(other)
        b = app.register_job(second, other, 'history', callback_b)
        self.assertIs(app.process, second)
        self.assertEqual(str(app.account_combo['state']), 'readonly')
        app.job_log(a, '50% 100/200')
        self.assertEqual(app.jobs[a]['progress'], '50% 100/200')
        self.assertEqual(app.account_progress.get(), 0)
        app.refresh_profiles(self.config)
        self.assertEqual(app.account_progress.get(), 50)
        app.refresh_profiles(other)
        self.assertEqual(app.account_progress.get(), 0)
        self.assertNotIn('50% 100/200', app.jobs[b]['logs'])
        with patch('desktop.subprocess.run') as kill:
            app.stop_job(a, confirm=False)
            if __import__('os').name == 'nt':
                self.assertEqual(kill.call_args.args[0][2], str(first.pid))
            else:
                first.terminate.assert_called_once()
        second.terminate.assert_not_called()
        app.events.put(('done', (a, 1, None)))
        app.events.put(('done', (b, 0, [])))
        app.poll_events()
        callback_a.assert_called_once_with(1, None)
        callback_b.assert_called_once_with(0, [])
        self.assertEqual(app.jobs[a]['state'], '失败 / 已停止')
        self.assertEqual(app.jobs[b]['state'], '完成')
        self.assertIsNone(app.process)

    def test_other_accounts_read_results_do_not_replace_current_history(self):
        from unittest.mock import Mock
        app = self.app
        callback = Mock()
        process = Mock()
        job = app.register_job(process, self.config, 'terms', callback)
        other = self.lib.save_profile({'username': 'second', 'school_host': 'http://127.0.0.1:8088/m-api'})
        app.refresh_profiles(other)
        app.events.put(('done', (job, 0, [{'key': 'private term'}])))
        app.poll_events()
        callback.assert_not_called()
        self.assertEqual(app.term_items, [])

    def test_two_real_workers_finish_out_of_order_without_network(self):
        import time
        app = self.app
        worker = self.folder/'desktop_worker.py'
        worker.write_text("import sys,time,json\nfrom pathlib import Path\nname=Path(sys.argv[sys.argv.index('--config')+1]).stem\ntime.sleep(0.3 if name=='demo_test' else 0.05)\nprint('worker '+name,flush=True)\nprint('DESKTOP_RESULT='+json.dumps({'account':name}),flush=True)\n", encoding='utf-8')
        other = self.lib.save_profile({'username': 'parallel', 'school_host': 'http://127.0.0.1:8088/m-api'})
        results = []
        with patch('socket.socket', side_effect=AssertionError('network forbidden')):
            a = app.start_job('auth', [], lambda code, result: results.append(('a', code, result)), always_callback=True)
            app.refresh_profiles(other)
            b = app.start_job('auth', [], lambda code, result: results.append(('b', code, result)), always_callback=True)
            try:
                deadline = time.monotonic()+8
                while len(results) < 2 and time.monotonic() < deadline:
                    app.update()
                    time.sleep(0.02)
                self.assertEqual({r[0]: r[2]['account'] for r in results}, {'a': 'demo_test', 'b': 'parallel'})
                self.assertTrue(all(r[1] == 0 for r in results))
                self.assertIn('worker demo_test', app.jobs[a]['logs'])
                self.assertNotIn('worker parallel', app.jobs[a]['logs'])
                self.assertIn('worker parallel', app.jobs[b]['logs'])
                self.assertIsNone(app.process)
            finally:
                for key in (a, b):
                    process = app.jobs[key]['process']
                    if process.poll() is None:
                        process.terminate()
                    process.wait(timeout=5)

    def test_no_profile_initial_launch(self):
        other = self.folder/'empty'
        other.mkdir()
        shutil.copyfile(ROOT/'config.example.ini', other/'config.example.ini')
        from desktop import Desktop
        window = Desktop(other)
        window.withdraw()
        try:
            self.assertIsNone(window.profile_path)
            self.assertEqual(window.account_var.get(), '')
            window.new_profile()
            self.assertIn('127.0.0.1', window.account_fields['school_host'].get())
        finally:
            window.destroy()


if __name__ == '__main__':
    unittest.main()
