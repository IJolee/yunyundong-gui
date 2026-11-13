import contextlib
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import desktop_core as core
from desktop_worker import history_request, flatten_history
from build_public_release import demo_route
from tools.generate_test_fixture import build_fixture
import random


class DesktopCoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copyfile(core.ROOT/'config.example.ini', self.root/'config.example.ini')
        self.library = core.Library(self.root)
        self.values = dict(username='demo_test', password='sample-password', token='sample-token',
                           device_id='sample-device', device_name='Demo', sys_edition='17', uuid='sample-uuid',
                           app_edition='3.6.7', school_host='http://127.0.0.1:8088/m-api', map_key='')

    def test_profiles_do_not_overwrite_each_other(self):
        first = self.library.save_profile(self.values)
        before = first.read_bytes()
        second = self.library.save_profile(dict(self.values, username='second', token='other-token'))
        self.assertEqual(first.read_bytes(), before)
        self.assertEqual(self.library.profile_values(second)['token'], 'other-token')
        self.assertEqual(len(self.library.profiles()), 2)
        with self.assertRaises(ValueError):
            self.library.save_profile(self.values)
        with self.assertRaises(ValueError):
            self.library.save_profile(dict(self.values, username='../escape'))

    def test_parse_headers_and_redaction(self):
        parsed = core.parse_headers('token: hello\ndeviceId: abc\nHost: 127.0.0.1:8088\nversion: 3.6.7\nsysVersion: 17')
        self.assertEqual(parsed['school_host'], 'http://127.0.0.1:8088/m-api')
        self.assertEqual(parsed['sys_edition'], '17')
        self.assertNotIn('sample-token', core.redact('server echoed sample-token', ['sample-token']))
        self.assertNotIn('abc', core.redact('token: abc'))

    def test_import_generate_and_record_local_only(self):
        source = self.root/'input.json'
        source.write_text(json.dumps(demo_route(150, 4)), encoding='utf-8')
        before = source.read_bytes()
        imported = self.library.import_route(source, 'demo_test')
        params = dict(mode='walk', distance_km='1.5', pace_min='5', pace_max='7', walk_pace='9', cadence='115', variation='5', seed='12')
        with patch('socket.socket', side_effect=AssertionError('network forbidden')):
            path = self.library.generate(params, imported, account='demo_test')
        d = json.loads(path.read_text(encoding='utf-8'))['data']
        self.assertEqual((d['recordMileage'], d['duration'], d['recodePace'], d['recodeCadence']), (1.5, 810, 9, 115))
        self.assertAlmostEqual(float(d['pointsList'][-1]['runMileage']), 1500)
        self.assertEqual(source.read_bytes(), before)
        self.library.record_status(path, '已测试')
        self.assertEqual(core.Library(self.root).state['records'][-1]['status'], '已测试')

    def test_generalized_parameters_and_rejection(self):
        source = demo_route(150, 4)
        result = build_fixture(source, random.Random(1), True, distance_km=1.0, pace_min=6, pace_max=6, cadence=160)
        d = result['data']
        self.assertEqual((d['duration'], d['recodePace'], d['recodeCadence']), (360, 6, 160))
        for options in ({'distance_km': 0}, {'pace_min': 9, 'pace_max': 5}, {'cadence': float('nan')}, {'variation': 2}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                build_fixture(source, random.Random(1), **options)

    def test_history_json_gzip_and_monthly_lists(self):
        value = {'code': 200, 'data': {'pointsList': []}}
        app = SimpleNamespace(default_post=lambda *a, **kw: json.dumps(value))
        self.assertEqual(history_request(app, '/history'), value)
        def encrypted(*a, **kw):
            kw['key_ctx']['key'] = 'demo-key'
            return 'fake-cipher'
        app = SimpleNamespace(default_post=encrypted, b64decode=lambda k: b'key',
                              decrypt_sm4=lambda text, key: gzip.compress(json.dumps(value).encode('utf-8')))
        self.assertEqual(history_request(app, '/history'), value)
        def quoted_encrypted(*a, **kw):
            kw['key_ctx']['key'] = 'demo-key'
            return json.dumps('fake-cipher')
        app.default_post = quoted_encrypted
        self.assertEqual(history_request(app, '/history'), value)
        self.assertEqual(flatten_history({'rank': [{'rankList': [{'id': 1}]}]}), [{'id': 1}])
        self.assertEqual(flatten_history({'records': [{'id': 2}]}), [{'id': 2}])

    def test_clean_template(self):
        c = core.read_conf(core.ROOT/'config.example.ini')
        for section in ('Login', 'User'):
            self.assertTrue(all(not value for _, value in c.items(section)))
        self.assertIn('127.0.0.1', c.get('Yun', 'school_host'))


if __name__ == '__main__':
    unittest.main()
