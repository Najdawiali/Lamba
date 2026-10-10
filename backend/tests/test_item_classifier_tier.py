"""
Tests for the service tier of the item classifier: merchant screens (add, rename, CSV upload) use the
interactive tier setting, batch jobs use the batch one. The real item_classifier.py runs against stand-ins
for httpx, app.config and the model adapter (tests/stub_modules.py): no network.
"""

import ast
import asyncio
import json
import os
import sys
import unittest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stub_modules import make_config, make_httpx, make_module, stubbed  # noqa: E402

from app.taxonomy import LEAF_CATEGORIES  # noqa: E402

PRODUCT_SLUG = next(c.slug for c in LEAF_CATEGORIES if c.listing_type == "product")
FRESH = ("app.services.http_pool", "app.services.item_classifier")


class FakeAdapter:
    def __init__(self):
        self.calls, self.fail_models = [], set()

    async def complete_chat(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["model"] in self.fail_models:
            return None
        return json.dumps({"restricted": "none", "category": PRODUCT_SLUG})

    def by_model(self):
        return {call["model"]: call for call in self.calls}


class TestClassifierTier(unittest.TestCase):
    def setUp(self):
        self.adapter = FakeAdapter()
        self.config = make_config(
            classifier_model="google/gemma-4-26B-A4B-it", classifier_secondary_model="google/gemma-4-31B-it",
            classifier_service_tier_interactive="priority", classifier_service_tier_batch="",
        )
        stubs = {
            "httpx": make_httpx(),
            "app.config": self.config,
            "app.services.llm": make_module("app.services.llm", llm_adapter=self.adapter),
        }
        self.stack = stubbed(stubs, fresh=FRESH)
        self.stack.__enter__()
        from app.services import item_classifier
        self.classifier = item_classifier

    def tearDown(self):
        self.stack.__exit__(None, None, None)

    def classify(self, **kwargs):
        return asyncio.run(self.classifier.classify_item_ensemble("حليب المراعي 1 لتر", None, "product", **kwargs))

    def test_a_batch_job_uses_the_standard_tier_by_default(self):
        result = self.classify()
        self.assertEqual(len(self.adapter.calls), 2)
        for call in self.adapter.calls:
            self.assertNotIn("service_tier", call)
        self.assertEqual((result.moderation_status, result.category_slug), ("approved", PRODUCT_SLUG))

    def test_a_merchant_screen_uses_priority_for_both_models(self):
        result = self.classify(interactive=True)
        by_model = self.adapter.by_model()
        self.assertEqual(set(by_model), {"google/gemma-4-26B-A4B-it", "google/gemma-4-31B-it"})
        for call in by_model.values():
            self.assertEqual(call["service_tier"], "priority")
            self.assertEqual(call["max_retries"], 1)                      # the rest of the call is unchanged
            self.assertIs(call["breaker"], self.classifier.deepinfra_catalog_breaker)
        self.assertEqual(result.moderation_status, "approved")

    def test_the_two_paths_have_their_own_settings(self):
        self.config.settings.classifier_service_tier_interactive = ""
        self.config.settings.classifier_service_tier_batch = "priority"
        self.classify(interactive=True)
        self.classify()
        interactive_calls, batch_calls = self.adapter.calls[:2], self.adapter.calls[2:]
        self.assertTrue(all("service_tier" not in c for c in interactive_calls))
        self.assertTrue(all(c["service_tier"] == "priority" for c in batch_calls))

    def test_flex_is_for_batch_jobs_only(self):
        self.config.settings.classifier_service_tier_interactive = "flex"
        self.config.settings.classifier_service_tier_batch = "flex"
        self.classify(interactive=True)
        self.classify()
        interactive_calls, batch_calls = self.adapter.calls[:2], self.adapter.calls[2:]
        self.assertTrue(all("service_tier" not in c for c in interactive_calls))   # a screen must not wait 10 minutes
        self.assertTrue(all(c["service_tier"] == "flex" for c in batch_calls))

    def test_a_typo_in_the_setting_does_not_break_classification(self):
        self.config.settings.classifier_service_tier_interactive = "prioriti"
        result = self.classify(interactive=True)
        self.assertTrue(all("service_tier" not in c for c in self.adapter.calls))
        self.assertEqual(result.moderation_status, "approved")

    def test_a_single_model_call_is_on_the_standard_tier_unless_asked(self):
        asyncio.run(self.classifier.classify_item("حليب", None, "product"))                       # the offline evals
        asyncio.run(self.classifier.classify_item("حليب", None, "product", service_tier="priority"))
        self.assertNotIn("service_tier", self.adapter.calls[0])
        self.assertEqual(self.adapter.calls[1]["service_tier"], "priority")

    def test_failing_closed_is_unchanged_when_a_model_does_not_answer(self):
        self.adapter.fail_models = {"google/gemma-4-31B-it"}
        result = self.classify(interactive=True)
        self.assertEqual(result.moderation_status, "pending_review")      # any model failing -> review
        self.assertFalse(result.restriction_known)


class TestWhoIsInteractive(unittest.TestCase):
    """Which callers wait on a screen, read from the source (merchant_v1 is not importable without FastAPI)."""

    @staticmethod
    def ensemble_calls(relative_path):
        with open(os.path.join(BACKEND, relative_path), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        return [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "classify_item_ensemble"
        ]

    def test_every_merchant_screen_call_is_interactive(self):
        calls = self.ensemble_calls(os.path.join("app", "api", "merchant_v1.py"))
        self.assertEqual(len(calls), 3)  # rename, add a new item, CSV upload
        for call in calls:
            flags = {k.arg: ast.literal_eval(k.value) for k in call.keywords}
            self.assertEqual(flags.get("interactive"), True, ast.unparse(call))

    def test_the_catalog_import_stays_on_the_batch_tier(self):
        calls = self.ensemble_calls(os.path.join("app", "jobs", "import_catalog.py"))
        self.assertEqual(len(calls), 1)
        self.assertNotIn("interactive", {k.arg for k in calls[0].keywords})


class TestDefaults(unittest.TestCase):
    def test_settings_defaults(self):
        with open(os.path.join(BACKEND, "app", "config.py"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        defaults = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
                try:
                    defaults[node.target.id] = ast.literal_eval(node.value)
                except ValueError:
                    pass
        self.assertEqual(defaults["classifier_service_tier_interactive"], "priority")
        self.assertEqual(defaults["classifier_service_tier_batch"], "")
        self.assertEqual(defaults["query_llm_service_tier"], "priority")


if __name__ == "__main__":
    unittest.main(verbosity=2)
