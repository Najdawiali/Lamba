"""
Tests for app.services.password_policy. Pure functions: no network, no database.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.password_policy import MIN_TAIL_LENGTH, MSG, password_problem

ARABIC = re.compile(r"[؀-ۿ]")


def rule_code(password, **personal):
    """The code of the rule that refuses `password`, or None when it is accepted."""
    problem = password_problem(password, **personal)
    return problem[0] if problem else None


class TestPasswordPolicy(unittest.TestCase):
    def test_exact_blocklist_matches_stay_common(self):
        # "rasputin" and "password" are entries of common_passwords.txt ("password" is also in
        # LOCAL_WEAK); "Merchant" is only in LOCAL_WEAK. Case does not matter.
        for pw in ("rasputin", "Rasputin", "password", "PASSWORD", "Merchant"):
            self.assertEqual(rule_code(pw), "common", pw)
        self.assertEqual(password_problem("rasputin"), ("common", MSG["common"]))

    def test_common_word_with_short_tail_is_common_variant(self):
        # The tail is the run of trailing digits/symbols after the word: 1 to 3 characters here.
        # "password123" is not itself on the list, so Password123 is a variant, not an exact match.
        for pw in ("Rasputin_3", "Rasputin3", "Rasputin123", "Password123", "Lamba_12"):
            self.assertEqual(rule_code(pw), "common_variant", pw)
        self.assertEqual(password_problem("Rasputin_3"), ("common_variant", MSG["common_variant"]))

    def test_common_word_with_longer_tail_is_accepted(self):
        # A tail of 4+ characters, or one that ends in a letter, is not a trivial variant.
        for pw in ("Rasputin_3??", "Rasputin_37x", "Rasputin1234"):
            self.assertIsNone(password_problem(pw), pw)

    def test_tail_boundary_is_four_characters(self):
        self.assertEqual(MIN_TAIL_LENGTH, 4)
        self.assertEqual(rule_code("Rasputin_37"), "common_variant")  # tail "_37": 3 characters
        self.assertIsNone(password_problem("Rasputin_374"))           # tail "_374": 4 characters

    def test_passphrases_are_accepted(self):
        for pw in ("correct horse battery staple", "purple-tractor-ocean-1987"):
            self.assertIsNone(password_problem(pw), pw)

    def test_other_rules_still_apply(self):
        self.assertEqual(rule_code("Ras_3"), "too_short")
        self.assertEqual(rule_code("كلمة_المرور_123"), "not_english")
        self.assertEqual(rule_code("a1" * 40), "too_long")
        self.assertEqual(rule_code("abcdefghij"), "pattern")
        self.assertEqual(rule_code("Zq7#unique-9", email="unique.person@example.com"), "personal")

    def test_messages_are_bilingual_arabic_then_english(self):
        # mobile/utils/serverMessage.ts splits on a newline and shows the line for the app's language.
        for key, message in MSG.items():
            lines = message.split("\n")
            self.assertEqual(len(lines), 2, key)
            self.assertTrue(ARABIC.search(lines[0]), key)
            self.assertFalse(ARABIC.search(lines[1]), key)


if __name__ == "__main__":
    unittest.main(verbosity=2)
