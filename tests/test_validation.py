import unittest

from castilla_bot.validation import normalize_email, normalize_whatsapp


class ContactValidationTests(unittest.TestCase):
    def test_email_normalizes_domain_and_rejects_invalid_format(self):
        self.assertEqual(normalize_email("  Aluna@Example.COM  "), "Aluna@example.com")
        for address in ("sem-arroba", "a@", "@example.com", "a@-example.com", "a@example", "a..b@example.com", "a b@example.com"):
            with self.subTest(address=address):
                self.assertIsNone(normalize_email(address))

    def test_whatsapp_requires_brazilian_ddd_and_normalizes_country_code(self):
        self.assertEqual(normalize_whatsapp("(61) 99999-9999"), "5561999999999")
        self.assertEqual(normalize_whatsapp("+55 61 99999-9999"), "5561999999999")
        self.assertEqual(normalize_whatsapp("11 3333-4444"), "551133334444")
        for number in ("99999-9999", "(00) 99999-9999", "(61) 00000-0000", "+1 202 555 0100", "61abc999999999"):
            with self.subTest(number=number):
                self.assertIsNone(normalize_whatsapp(number))


if __name__ == "__main__":
    unittest.main()
