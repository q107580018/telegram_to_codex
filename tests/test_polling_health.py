import unittest

from app.config.polling_health import PollingHealthManager


class PollingHealthManagerTests(unittest.TestCase):
    def test_enters_degraded_after_single_network_error(self):
        mgr = PollingHealthManager(
            restart_threshold=3,
            restart_cooldown_sec=20.0,
            max_restarts_per_window=4,
            restart_window_sec=300.0,
        )

        decision = mgr.record_network_error(now=100.0)

        self.assertEqual(mgr.state, "degraded")
        self.assertEqual(mgr.consecutive_network_errors, 1)
        self.assertFalse(decision.should_restart_polling)
        self.assertFalse(decision.should_escalate_process)

    def test_triggers_restart_when_threshold_reached_and_not_in_cooldown(self):
        mgr = PollingHealthManager(3, 20.0, 4, 300.0)

        mgr.record_network_error(now=100.0)
        mgr.record_network_error(now=101.0)
        decision = mgr.record_network_error(now=102.0)

        self.assertTrue(decision.should_restart_polling)
        self.assertFalse(decision.should_escalate_process)
        self.assertEqual(mgr.state, "recovering")
        self.assertEqual(mgr.restart_timestamps, [102.0])

    def test_blocks_restart_inside_cooldown(self):
        mgr = PollingHealthManager(1, 20.0, 4, 300.0)

        first = mgr.record_network_error(now=100.0)
        second = mgr.record_network_error(now=110.0)

        self.assertTrue(first.should_restart_polling)
        self.assertFalse(second.should_restart_polling)
        self.assertGreater(second.next_retry_sec, 0)

    def test_escalates_when_restart_count_exceeds_window_limit(self):
        mgr = PollingHealthManager(1, 0.0, 2, 300.0)

        mgr.record_network_error(now=100.0)
        mgr.record_network_error(now=110.0)
        decision = mgr.record_network_error(now=120.0)

        self.assertTrue(decision.should_escalate_process)
        self.assertFalse(decision.should_restart_polling)
        self.assertEqual(mgr.state, "escalated")

    def test_mark_healthy_resets_consecutive_errors(self):
        mgr = PollingHealthManager(3, 20.0, 4, 300.0)
        mgr.record_network_error(now=100.0)

        mgr.mark_healthy(now=111.0)

        self.assertEqual(mgr.state, "healthy")
        self.assertEqual(mgr.consecutive_network_errors, 0)

    def test_snapshot_contains_restart_window_count(self):
        mgr = PollingHealthManager(1, 0.0, 4, 100.0)
        mgr.record_network_error(now=100.0)
        mgr.record_network_error(now=150.0)

        snapshot = mgr.snapshot(now=210.0)

        self.assertEqual(snapshot["restarts_in_window"], 1)
        self.assertEqual(snapshot["state"], "recovering")


if __name__ == "__main__":
    unittest.main()
