"""
Tests for app.services.service_tier: which request fields a configured DeepInfra tier becomes.
Pure functions: no network.
"""

import logging
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import service_tier
from app.services.service_tier import service_tier_fields


class TestServiceTierFields(unittest.TestCase):
    def setUp(self):
        service_tier._warned.clear()

    def test_the_standard_tier_adds_nothing(self):
        for value in (None, "", "   ", "standard", "Standard", "default", "none"):
            self.assertEqual(service_tier_fields(value), {}, repr(value))

    def test_priority_and_flex_are_sent_as_given(self):
        self.assertEqual(service_tier_fields("priority"), {"service_tier": "priority"})
        self.assertEqual(service_tier_fields(" Priority "), {"service_tier": "priority"})
        self.assertEqual(service_tier_fields("flex"), {"service_tier": "flex"})

    def test_flex_is_refused_on_an_interactive_path(self):
        with self.assertLogs(service_tier.logger, level=logging.WARNING) as logs:
            self.assertEqual(service_tier_fields("flex", allow_flex=False), {})
        self.assertIn("flex", logs.output[0])
        self.assertEqual(service_tier_fields("priority", allow_flex=False), {"service_tier": "priority"})

    def test_a_typo_is_ignored_with_one_warning_instead_of_failing_every_call(self):
        with self.assertLogs(service_tier.logger, level=logging.WARNING) as logs:
            self.assertEqual(service_tier_fields("prioriti"), {})
            self.assertEqual(service_tier_fields("prioriti"), {})
            self.assertEqual(service_tier_fields("turbo"), {})
        self.assertEqual(len(logs.output), 2)  # one per distinct value
        self.assertIn("prioriti", logs.output[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
