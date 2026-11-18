import unittest
from unittest.mock import patch
from tools import runtime_guard as guard


class RuntimeGuardTests(unittest.TestCase):
    def test_power_state_restored_on_error(self):
        with patch.object(guard.sys, 'platform', 'win32'), \
                patch.object(guard, '_set_execution_state', return_value=guard.ES_CONTINUOUS) as call:
            with self.assertRaises(ValueError):
                with guard.prevent_idle_sleep():
                    raise ValueError('simulated upload failure')
            self.assertEqual([c.args[0] for c in call.call_args_list],
                             [guard.ES_CONTINUOUS | guard.ES_SYSTEM_REQUIRED, guard.ES_CONTINUOUS])

    def test_normal_wait(self):
        values = iter([100, 124])
        sleeps = []
        guard.wait_between_batches(23.5, clock=lambda: next(values), sleep=sleeps.append)
        self.assertEqual(sleeps, [23.5])

    def test_long_pause_detected(self):
        values = iter([100, 3400])
        with self.assertRaisesRegex(RuntimeError, '暂停'):
            guard.wait_between_batches(23.5, clock=lambda: next(values), sleep=lambda _: None)


if __name__ == '__main__':
    unittest.main()
