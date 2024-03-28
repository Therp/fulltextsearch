# Copyright 2024 Therp BV <https://therp.nl>.
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html
from odoo.tests.common import TransactionCase


class TestFtsQueryHelper(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.query_helper = cls.env["fts.query.helper"]

    def test_single_word(self):
        parsed_string = self.query_helper.parse_searchstring("Rainbow")
        # Simple word should only be converted to lowercase.
        self.assertEqual(parsed_string, "rainbow")

    def test_multiple_words(self):
        parsed_string = self.query_helper.parse_searchstring("Rainbow Warrior")
        # Multiple words should be linked with '&'.
        self.assertEqual(parsed_string, "rainbow & warrior")

    def test_quoted_strings(self):
        parsed_string = self.query_helper.parse_searchstring("The Film 'Finding Nemo'")
        # Words in quoted strings should be joined with '<->'.
        self.assertEqual(parsed_string, "the & film & finding<->nemo")

    def test_substrings(self):
        parsed_string = self.query_helper.parse_searchstring("Rainbow* Warrior:* Ship")
        # Words in quoted strings should be joined with '<->'.
        self.assertEqual(parsed_string, "rainbow:* & warrior:* & ship")

    def test_and_or_words(self):
        parsed_string = self.query_helper.parse_searchstring(
            "Rainbow or Warrior and Film & Afghanistan"
        )
        # Multiple words should be linked with '&'.
        self.assertEqual(parsed_string, "rainbow | warrior & film & afghanistan")
