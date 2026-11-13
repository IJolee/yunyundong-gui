import contextlib
import gzip
import io
import json
import random
import unittest
from unittest.mock import patch

from tools.generate_test_fixture import ROOT, build_fixture, distance


class WalkingFixtureTests(unittest.TestCase):
    def setUp(self):
        self.source = json.loads(((ROOT/'tasks_else/tasklist_9.json') if (ROOT/'tasks_else/tasklist_9.json').exists() else (ROOT/'demo_routes/tasklist_9.json')).read_text(encoding='utf-8'))

    def test_fifty_walking_profiles(self):
        for seed in range(50):
            fixture = build_fixture(self.source, random.Random(seed), randomize=True, mode='walk')
            d = fixture['data']
            pts = d['pointsList']
            self.assertEqual(fixture['motion_mode'], 'walk')
            self.assertEqual((d['recordMileage'], d['duration'], d['recodePace']), (2, 1080, 9))
            self.assertEqual(d['recodeCadence'], 120)
            self.assertEqual(int(pts[-1]['runTime']), 1080)
            self.assertEqual(int(pts[-1]['runStep']), 2160)
            self.assertAlmostEqual(d['strides']*int(pts[-1]['runStep']), 2000)
            paces = [p['speed'] for p in pts]
            self.assertTrue(all(8 <= p <= 10 for p in paces))
            self.assertGreater(len(set(paces)), 1)
            integrated = 0.0
            for a, b in zip(pts, pts[1:]):
                meters = float(b['runMileage'])-float(a['runMileage'])
                self.assertLessEqual(int(a['runTime']), int(b['runTime']))
                integrated += meters*(a['speed']+b['speed'])/2*60/1000
                self.assertLessEqual(abs(b['speed']-a['speed']), meters*0.002+1e-7)
            self.assertLess(abs(integrated-1080), 0.001)
            coords = [tuple(map(float, p['point'].split(','))) for p in pts]
            self.assertLess(abs(sum(distance(a, b) for a, b in zip(coords, coords[1:]))-2000), 0.001)

    def test_walking_batch_uses_walking_cadence_and_stride(self):
        import main as app
        fixture = build_fixture(self.source, random.Random(4), randomize=True, mode='walk')
        runner = object.__new__(app.Yun_For_New)
        runner.task_map = fixture
        runner.crsRunRecordId = 'test-record'
        runner.schoolId = 100
        runner.userName = 'test-user'
        with patch.object(app, 'default_post', return_value='{"code":200}') as post, \
                contextlib.redirect_stdout(io.StringIO()):
            runner.split_by_points_map(fixture['data']['pointsList'][:10])
        body = json.loads(gzip.decompress(post.call_args.args[1]))
        self.assertEqual(body['runSteps'], 120)
        self.assertAlmostEqual(body['strides'], fixture['data']['strides'])
        self.assertEqual(body['speeds'], 9)
        self.assertTrue(post.call_args.kwargs['isBytes'])

    def test_default_running_mode_retained(self):
        result = build_fixture(self.source, random.Random(4), randomize=True)
        self.assertEqual(result['motion_mode'], 'run')
        self.assertEqual(result['data']['recodeCadence'], 170)
        self.assertTrue(600 <= result['data']['duration'] <= 840)
        with self.assertRaises(ValueError):
            build_fixture(self.source, random.Random(4), mode='invalid')


if __name__ == '__main__':
    unittest.main()
