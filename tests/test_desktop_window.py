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
        self.assertEqual(len(app.tabs.tabs()), 5)
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
