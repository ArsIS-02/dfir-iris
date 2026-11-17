"""Regression tests for SOC canary self-assignment notifications."""

from types import SimpleNamespace
from unittest import TestCase

from app.business.alerts import _is_closed_soc_canary


def _alert(status_id=2, title='HEALTH - SOC canary: сквозная проверка [soc-canary-test]'):
    return SimpleNamespace(alert_status_id=status_id, alert_title=title)


class TestSocCanaryNotifications(TestCase):

    def test_closed_canary_is_suppressed(self):
        self.assertTrue(_is_closed_soc_canary(_alert(status_id=6)))

    def test_new_canary_is_not_suppressed(self):
        self.assertFalse(_is_closed_soc_canary(_alert(status_id=2)))

    def test_closed_regular_alert_is_not_suppressed(self):
        alert = _alert(status_id=6, title='Regular alert [soc-canary-test]')
        self.assertFalse(_is_closed_soc_canary(alert))

    def test_unrelated_closed_alert_is_not_suppressed(self):
        self.assertFalse(_is_closed_soc_canary(_alert(status_id=6, title='Regular alert')))
