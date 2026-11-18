"""离线回归：运行 python -m unittest discover -s tests -v。"""
import copy
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch
import contextlib
import io

from tools.generate_test_fixture import build_fixture, distance, ROOT


ROUTES = ROOT/'tasks_else' if (ROOT/'tasks_else/tasklist_9.json').exists() else ROOT/'demo_routes'
CONFIG = ROOT/'config.ini' if (ROOT/'config.ini').exists() else ROOT/'config.example.ini'


class FixtureGenerationTests(unittest.TestCase):
    def setUp(self):
        self.path = ROUTES/'tasklist_9.json'
        self.original_bytes = self.path.read_bytes()
        self.source = json.loads(self.original_bytes)

    def test_source_rhythm_and_time_scale_stay_together(self):
        result = build_fixture(self.source, random.Random(1))
        d = result['data']
        pts = d['pointsList']
        source = self.source['data']['pointsList']
        scale = ((float(pts[1]['speed'])/float(source[1]['speed'])))
        self.assertGreater(len(set(p['speed'] for p in pts)), 1)
        # 最后一点经过空间插值，其余点应完整保留源配速比例和相对时序。
        for old, new in zip(source, pts[:-1]):
            self.assertAlmostEqual(float(new['speed']), float(old['speed'])*scale)
            expected = (float(old['runTime'])-float(source[0]['runTime']))*scale
            self.assertLessEqual(abs(int(new['runTime'])-expected), 0.500001)

    def test_fixed_distance_and_random_average_pace(self):
        durations = set()
        for seed in range(50):
            d = build_fixture(self.source, random.Random(seed))['data']
            pts = d['pointsList']
            durations.add(d['duration'])
            self.assertEqual(d['recordMileage'], 2)
            self.assertTrue(600 <= d['duration'] <= 840)
            self.assertAlmostEqual(d['recodePace'], d['duration']/120)
            self.assertEqual(float(pts[-1]['runMileage']), 2000)
            self.assertEqual(int(pts[0]['runTime']), 0)
            self.assertEqual(int(pts[-1]['runTime']), d['duration'])
            coords = [tuple(map(float, p['point'].split(','))) for p in pts]
            measured = sum(distance(a, b) for a, b in zip(coords, coords[1:]))
            self.assertLess(abs(measured-2000), 0.001)
            for a, b in zip(pts, pts[1:]):
                self.assertLessEqual(int(a['runTime']), int(b['runTime']))
                self.assertEqual(int(b['ts'])-int(a['ts']), int(b['runTime'])-int(a['runTime']))
        self.assertGreater(len(durations), 1)

    def test_input_and_checkpoint_metadata_unchanged(self):
        before = copy.deepcopy(self.source)
        result = build_fixture(self.source, random.Random(1))
        self.assertEqual(self.source, before)
        self.assertEqual(self.path.read_bytes(), self.original_bytes)
        for key in ('manageList', 'managePoints', 'recodeDislikes'):
            self.assertEqual(result['data'][key], before['data'][key])
        self.assertTrue(result['synthetic'])

    def test_invalid_source_is_rejected(self):
        for field, value in [('runTime', -1), ('speed', 0), ('speed', float('nan'))]:
            broken = copy.deepcopy(self.source)
            broken['data']['pointsList'][1][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                build_fixture(broken, random.Random(1))
        short = copy.deepcopy(self.source)
        short['data']['pointsList'] = short['data']['pointsList'][:2]
        with self.assertRaises(ValueError):
            build_fixture(short, random.Random(1))

    def test_random_windows_remain_continuous_and_exact(self):
        source = json.loads((ROUTES/'tasklist_6.json').read_text(encoding='utf-8'))
        starts = set()
        durations = set()
        max_source_segment = max(distance(tuple(map(float, a['point'].split(','))),
                                          tuple(map(float, b['point'].split(','))))
                                 for a, b in zip(source['data']['pointsList'], source['data']['pointsList'][1:]))
        for seed in range(50):
            result = build_fixture(source, random.Random(seed), randomize=True)
            starts.add(result['source_window_m']['start'])
            d = result['data']
            durations.add(d['duration'])
            self.assertTrue(600 <= d['duration'] <= 840)
            self.assertEqual(int(d['pointsList'][0]['runTime']), 0)
            self.assertEqual(int(d['pointsList'][-1]['runTime']), d['duration'])
            coords = [tuple(map(float, p['point'].split(','))) for p in d['pointsList']]
            segments = [distance(a, b) for a, b in zip(coords, coords[1:])]
            self.assertLess(abs(sum(segments)-2000), 0.001)
            self.assertLessEqual(max(segments), max_source_segment+0.001)
            self.assertGreater(len(set(p['speed'] for p in d['pointsList'])), 1)
            self.assertTrue(all(int(a['runTime']) <= int(b['runTime'])
                                for a, b in zip(d['pointsList'], d['pointsList'][1:])))
        self.assertGreater(len(starts), 40)
        self.assertGreater(len(durations), 1)

    def test_random_seed_reproducible(self):
        a = build_fixture(self.source, random.Random(42), randomize=True)
        b = build_fixture(self.source, random.Random(42), randomize=True)
        c = build_fixture(self.source, random.Random(43), randomize=True)
        self.assertEqual(a, b)
        self.assertNotEqual(a['source_window_m'], c['source_window_m'])
        self.assertNotEqual(a['rhythm_factors'], c['rhythm_factors'])

    def test_default_entry_selects_multiple_routes_without_network(self):
        import upload_test as entry
        sources = ROUTES
        before = {p: p.read_bytes() for p in sources.glob('*.json')}
        chosen = set()
        with tempfile.TemporaryDirectory() as folder, patch.object(entry, 'ROOT', Path(folder)), \
                patch('socket.socket', side_effect=AssertionError('network forbidden')), \
                contextlib.redirect_stdout(io.StringIO()):
            for seed in range(12):
                path = entry.generate_local(CONFIG, seed=seed, source_dir=sources)
                fixture = json.loads(path.read_text(encoding='utf-8'))
                chosen.add(fixture['source_file'])
                original = json.loads(Path(fixture['source_file']).read_text(encoding='utf-8'))
                self.assertEqual(fixture['data']['manageList'], original['data']['manageList'])
        self.assertGreater(len(chosen), 1)
        self.assertTrue(all(p.read_bytes() == body for p, body in before.items()))


if __name__ == '__main__':
    unittest.main()
