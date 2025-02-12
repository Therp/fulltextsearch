# Copyright 2024 Therp BV <https://therp.nl>.
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
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

    def test_patch_where_clause(self):
        ORIGINAL_WHERE = (
            """("ir_attachment"."res_field" IS NULL)"""
            """ AND ("ir_attachment"."content_tsvector"::text """
            """= %s)"""
        )
        MODIFIED_WHERE = (
            """("ir_attachment"."res_field" IS NULL)"""  # same
            """ AND ("ir_attachment"."content_tsvector" """  # no more ::text
            """@@ to_tsquery('simple', %s))"""  # replaced
        )
        modified_where_clause = self.query_helper.patch_where_clause(
            ORIGINAL_WHERE, "ir_attachment", "content_tsvector"
        )
        self.assertEqual(modified_where_clause, MODIFIED_WHERE)
        # Replace should also succeed it it does not contain ::text
        modified_original = ORIGINAL_WHERE.replace("::text", "")
        modified_where_clause = self.query_helper.patch_where_clause(
            modified_original, "ir_attachment", "content_tsvector"
        )
        self.assertEqual(modified_where_clause, MODIFIED_WHERE)

    def test_get_model_and_field(self):
        start_model = self.env["res.users"]
        dotted_field_name = "partner_id.parent_id.company_id.name"
        end_model, field_name = self.query_helper.get_model_and_field(
            start_model, dotted_field_name
        )
        self.assertEqual(end_model, self.env["res.company"])
        self.assertEqual(field_name, "name")

    def test_fts_patch_domain(self):
        model = self.env["fts.content"]
        domain = [
            ("date", ">=", "2001-01-01"),
            "|",
            ("name", "ilike", "Herman"),
            ("content_tsvector", "=", "Piet or Jan"),
        ]
        fulltext_leaves, modified_domain = self.query_helper.fts_patch_domain(
            model, domain
        )
        self.assertEqual(fulltext_leaves, [("fts_content", "content_tsvector")])
        self.assertEqual(modified_domain[1], "|")
        self.assertEqual(modified_domain[3], ("content_tsvector", "=", "piet | jan"))
