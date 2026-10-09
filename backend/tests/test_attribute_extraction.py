"""
Tests for app.services.attribute_extraction: the prompt, the response schema, the parser and the
validator. Pure functions plus a fake model call: no network, no database.
"""

import asyncio
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.attribute_extraction import (
    DIETARY_VALUES,
    EXTRACT_KEYS,
    MAX_NAME_LENGTH,
    PROMPT_VERSION,
    RESPONSE_FORMATS,
    RESPONSE_SCHEMA,
    USER_PROMPT,
    build_messages,
    extract_attributes,
    parse_json_object,
    validate_extracted,
)
from app.services.attribute_rules import SEARCH_ATTR_KEYS, canonical_enum_value


def clean(raw, name, **kw):
    return validate_extracted(raw, name, **kw)[0]


def dropped(raw, name, **kw):
    return validate_extracted(raw, name, **kw)[1]


class TestAttributeValidator(unittest.TestCase):
    def test_a_good_answer_passes_unchanged(self):
        raw = {"brand": "المراعي", "dietary": "قليل الدسم"}
        self.assertEqual(validate_extracted(raw, "حليب المراعي قليل الدسم 1 لتر"), (raw, []))

    def test_brand_must_be_written_in_the_name(self):
        self.assertEqual(clean({"brand": "نستله"}, "حليب المراعي"), {})
        self.assertEqual(dropped({"brand": "نستله"}, "حليب المراعي"), ["brand:not_in_name"])
        self.assertEqual(clean({"brand": "Lipton"}, "lipton yellow label tea"), {"brand": "Lipton"})
        # the name may carry the brand without the Arabic article
        self.assertEqual(clean({"brand": "المراعي"}, "حليب مراعي"), {"brand": "المراعي"})

    def test_organic_is_only_true_and_only_with_evidence(self):
        self.assertEqual(clean({"organic": True}, "زيت زيتون عضوي"), {"organic": True})
        self.assertEqual(clean({"organic": True}, "Organic honey"), {"organic": True})
        self.assertEqual(dropped({"organic": True}, "زيت زيتون بكر"), ["organic:no_evidence"])
        for bad in (False, "true", "yes", 1, [True]):
            self.assertEqual(dropped({"organic": bad}, "زيت زيتون عضوي"), ["organic:not_true"], repr(bad))
        # "bio" must be a whole word: Biscuit is not organic
        self.assertEqual(clean({"organic": True}, "Biscuit chocolate"), {})

    def test_gender_needs_a_gender_word_for_that_gender(self):
        self.assertEqual(clean({"gender": "female"}, "مزيل عرق نسائي نيفيا 150 مل"), {"gender": "female"})
        self.assertEqual(clean({"gender": "male"}, "Men Perfume Dior 100ml"), {"gender": "male"})
        self.assertEqual(clean({"gender": "unisex"}, "عطر للجنسين"), {"gender": "unisex"})
        self.assertEqual(dropped({"gender": "male"}, "مزيل عرق نسائي"), ["gender:no_evidence"])
        # "men" inside "women" is not evidence of male
        self.assertEqual(dropped({"gender": "male"}, "Women Perfume"), ["gender:no_evidence"])
        for bad in ("robot", "any", 3):
            self.assertEqual(dropped({"gender": bad}, "عطر نسائي"), ["gender:bad_value"], repr(bad))
        # Arabic from the model is canonicalised before it is stored
        self.assertEqual(clean({"gender": "نسائي"}, "عطر نسائي"), {"gender": "female"})

    def test_temperature_needs_a_temperature_word(self):
        self.assertEqual(clean({"temperature": "cold"}, "قهوة باردة"), {"temperature": "cold"})
        self.assertEqual(clean({"temperature": "iced"}, "Iced Tea Peach"), {"temperature": "iced"})
        self.assertEqual(dropped({"temperature": "hot"}, "قهوة باردة"), ["temperature:no_evidence"])
        self.assertEqual(dropped({"temperature": "lukewarm"}, "قهوة باردة"), ["temperature:bad_value"])

    def test_dietary_is_a_closed_list_backed_by_the_name(self):
        self.assertEqual(clean({"dietary": "بدون سكر"}, "عصير بدون سكر"), {"dietary": "بدون سكر"})
        self.assertEqual(clean({"dietary": "بدون سكر"}, "Coca-Cola Zero 330ml"), {"dietary": "بدون سكر"})
        self.assertEqual(clean({"dietary": "خالي من الغلوتين"}, "معكرونة خالية من الغلوتين"),
                         {"dietary": "خالي من الغلوتين"})
        self.assertEqual(dropped({"dietary": "low fat"}, "Low fat milk"), ["dietary:not_canonical"])
        self.assertEqual(dropped({"dietary": "قليل الدسم"}, "حليب المراعي"), ["dietary:no_evidence"])
        self.assertTrue(all(value in DIETARY_VALUES for value in ("قليل الدسم", "كامل الدسم", "نباتي")))

    def test_short_arabic_words_for_the_text_keys(self):
        self.assertEqual(clean({"type": "أخضر", "origin": "صيني"}, "شاي أخضر صيني"), {"type": "أخضر", "origin": "صيني"})
        self.assertEqual(clean({"type": "بكر ممتاز"}, "زيت زيتون بكر ممتاز"), {"type": "بكر ممتاز"})
        cases = {
            "several_values": "أخضر/green",
            "has_digit": "500 مل",
            "not_arabic": "green",
            "placeholder": "منتج",
            "too_many_words": "أخضر صيني فاخر جدا",
            "not_a_short_string": ["أخضر"],
        }
        for reason, value in cases.items():
            self.assertEqual(dropped({"type": value}, "شاي أخضر صيني فاخر"), ["type:" + reason], reason)
        self.assertEqual(dropped({"type": "شاي أخضر"}, "شاي أخضر"), ["type:equals_name"])

    def test_nothing_is_stored_for_unknown_or_disabled_keys(self):
        self.assertEqual(clean({"size": "500 مل", "price": 5}, "حليب 500 مل"), {})
        self.assertEqual(dropped({"size": "500 مل"}, "حليب 500 مل"), ["size:unknown_key"])
        self.assertEqual(clean({"brand": "المراعي", "type": "كامل"}, "حليب المراعي كامل", keys=("brand",)),
                         {"brand": "المراعي"})
        self.assertEqual(dropped({"type": "كامل"}, "حليب كامل", keys=("brand",)), ["type:key_disabled"])

    def test_empty_values_are_ignored_quietly(self):
        self.assertEqual(validate_extracted({"brand": None, "type": "", "flavor": None}, "ماء"), ({}, []))
        self.assertEqual(validate_extracted({}, "ماء"), ({}, []))

    def test_an_answer_that_is_not_an_object_is_refused(self):
        for raw in (None, [], "text", 5):
            self.assertEqual(validate_extracted(raw, "ماء"), ({}, ["not_an_object"]), repr(raw))


class TestAttributeJsonParser(unittest.TestCase):
    def test_plain_fenced_and_chatty_replies(self):
        self.assertEqual(parse_json_object('{"brand": "ليز"}'), {"brand": "ليز"})
        self.assertEqual(parse_json_object('```json\n{"brand": "ليز"}\n```'), {"brand": "ليز"})
        self.assertEqual(parse_json_object('<think>hmm {x}</think>{"flavor": "جبنة"}'), {"flavor": "جبنة"})
        self.assertEqual(parse_json_object('Here you go: {"origin": "أردني"} hope it helps'), {"origin": "أردني"})
        self.assertEqual(parse_json_object("{}"), {})

    def test_things_that_are_not_an_object(self):
        for text in (None, "", "no json here", "[1, 2]", '{"broken": ', "}{"):
            self.assertIsNone(parse_json_object(text), repr(text))


class TestAttributeExtract(unittest.TestCase):
    def run_extract(self, reply, name="حليب المراعي قليل الدسم", **kw):
        calls = []

        async def call_chat(messages, response_format):
            calls.append((messages, response_format))
            if isinstance(reply, Exception):
                raise reply
            return reply

        result = asyncio.run(extract_attributes(name, call_chat, **kw))
        return result, calls

    @staticmethod
    def payload(content, **extra):
        data = {"choices": [{"message": {"content": content}}], "usage": {"prompt_tokens": 900, "completion_tokens": 25}}
        data.update(extra)
        return data

    def test_a_good_reply_is_validated_and_the_tokens_counted(self):
        result, calls = self.run_extract(
            self.payload('{"brand": "المراعي", "dietary": "قليل الدسم", "type": "A1"}'),
            response_format=RESPONSE_FORMATS["schema"],
        )
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.attributes, {"brand": "المراعي", "dietary": "قليل الدسم"})
        self.assertEqual(result.dropped, ["type:has_digit"])
        self.assertEqual((result.prompt_tokens, result.completion_tokens), (900, 25))
        ((messages, response_format),) = calls
        self.assertIs(response_format, RESPONSE_FORMATS["schema"])
        self.assertEqual([m["role"] for m in messages], ["system", "user"])
        self.assertIn("حليب المراعي قليل الدسم", messages[1]["content"])

    def test_an_empty_object_is_a_real_answer(self):
        result, _ = self.run_extract(self.payload("{}"))
        self.assertEqual((result.status, result.attributes, result.dropped), ("ok", {}, []))

    def test_failures_are_told_apart(self):
        self.assertEqual(self.run_extract(None)[0].status, "no_response")
        self.assertEqual(self.run_extract({})[0].status, "no_response")
        boom, _ = self.run_extract(RuntimeError("socket closed"))
        self.assertEqual((boom.status, boom.raw), ("no_response", "RuntimeError('socket closed')"))
        self.assertEqual(self.run_extract(self.payload("sorry, I cannot"))[0].status, "bad_json")
        self.assertEqual(self.run_extract({"choices": []})[0].status, "bad_json")
        self.assertEqual(self.run_extract({"choices": [{"message": None}]})[0].status, "bad_json")

    def test_reasoning_content_is_used_when_content_is_empty(self):
        reply = {"choices": [{"message": {"content": None, "reasoning_content": '{"brand": "ليز"}'}}]}
        result, _ = self.run_extract(reply, name="شيبس ليز")
        self.assertEqual((result.status, result.attributes), ("ok", {"brand": "ليز"}))
        self.assertEqual((result.prompt_tokens, result.completion_tokens), (0, 0))


class TestAttributePrompt(unittest.TestCase):
    def test_names_only(self):
        user = build_messages("شاي أخضر")[1]["content"]
        self.assertTrue(user.startswith("Product name: شاي أخضر"))
        for word in ("Description", "Category", "description:"):
            self.assertNotIn(word, user)

    def test_the_name_is_collapsed_and_capped(self):
        user = build_messages("  شاي \n\n  أخضر  " + "x" * 500)[1]["content"]
        self.assertTrue(user.startswith("Product name: شاي أخضر x"))
        self.assertNotIn("x" * (MAX_NAME_LENGTH + 1), user)

    def test_every_worked_example_in_the_prompt_passes_the_validator_unchanged(self):
        examples = [line for line in USER_PROMPT.splitlines() if line.startswith('"') and '" -> ' in line]
        self.assertGreaterEqual(len(examples), 6)
        for line in examples:
            name, expected = line[1:].split('" -> ', 1)
            expected = json.loads(expected)
            attributes, dropped_reasons = validate_extracted(expected, name)
            self.assertEqual((attributes, dropped_reasons), (expected, []), line)

    def test_schema_and_keys_agree_with_the_search_rules(self):
        self.assertEqual(set(RESPONSE_SCHEMA["properties"]), set(EXTRACT_KEYS))
        self.assertIs(RESPONSE_SCHEMA["additionalProperties"], False)
        self.assertTrue(set(EXTRACT_KEYS) <= SEARCH_ATTR_KEYS)
        self.assertNotIn("size", EXTRACT_KEYS)
        for key in ("gender", "temperature"):
            for value in RESPONSE_SCHEMA["properties"][key]["enum"]:
                self.assertEqual(canonical_enum_value(key, value), value)
        self.assertEqual(RESPONSE_SCHEMA["properties"]["organic"], {"type": "boolean"})
        self.assertEqual(set(RESPONSE_FORMATS), {"schema", "object", "none"})
        self.assertIsNone(RESPONSE_FORMATS["none"])
        self.assertIsInstance(PROMPT_VERSION, int)


if __name__ == "__main__":
    unittest.main(verbosity=2)
