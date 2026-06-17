# Copyright 2025 Therp BV <https://therp.nl>.
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

TEST_DATA = [
    ("Herman Gorter", "Een nieuwe lente, een nieuw geluid", "2024-12-12"),
    (
        "Henriëtte Roland-Holst",
        "De stilte der natuur heeft veel geluiden",
        "2024-12-13",
    ),
    ("Nikolay Chernyshevsky", "The spark will ignite the flame!", "1997-06-13"),
    ("PLSR motto", "Through struggle you will attain your rights!", "2025-01-23"),
]


@tagged("post_install", "-at_install")
class TestFtsQueryHelper(TransactionCase):
    @classmethod
    def _create_test_data(cls):
        """Make sure we have data to test."""
        vals_list = [
            {
                "name": tpl[0],
                "content": tpl[1],
                "date": tpl[2],
            }
            for tpl in TEST_DATA
        ]
        cls.content_model.create(vals_list)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.content_model = cls.env["fts.content"]
        cls._create_test_data()

    def test_search_basic(self):
        """Test search on name and on content."""
        records = self.content_model.search([("content_tsvector", "like", "geluid")])
        self.assertTrue(records)
        self.assertEqual(records[0].name, "Herman Gorter")

    def test_search_or(self):
        """Test search that should find two records through or condition."""
        domain = [("content_tsvector", "like", "flame or rights")]
        records = self.content_model.search(domain)
        self.assertTrue(records)
        for record in records:
            self.assertIn(record.name, ("Nikolay Chernyshevsky", "PLSR motto"))
        count = self.content_model.search_count(domain)
        self.assertEqual(count, 2)

    def test_proxy_search(self):
        proxy_model = self.env["fts.proxy"]
        domain = [
            ("res_model", "=", "fts.content"),
            ("searchstring", "like", "flame or rights"),
        ]
        records = proxy_model.search(domain, order="extra desc")
        self.assertTrue(records)
        for record in records:
            self.assertIn(record.res_name, ("Nikolay Chernyshevsky", "PLSR motto"))

    def test_proxy_rec_name_search(self):
        """Test combined search on text and rec_name."""
        proxy_model = self.env["fts.proxy"]
        domain = [
            ("res_model", "=", "fts.content"),
            ("searchstring", "like", "geluid*"),
            ("res_name", "like", "Henriëtte Roland-Holst"),
        ]
        records = proxy_model.search(domain, order="extra desc")
        self.assertTrue(records)
        self.assertEqual(records[0].res_name, "Henriëtte Roland-Holst")

    def test_ordered_search(self):
        proxy_model = self.env["fts.proxy"]
        domain = [
            ("res_model", "=", "fts.content"),
            ("searchstring", "like", "geluid or flame or rights"),
        ]
        records = proxy_model.search(domain, order="date desc")
        self.assertTrue(records)
        self.assertEqual(len(records), 3)
        self.assertEqual(records[0].res_name, "PLSR motto")
        self.assertEqual(records[1].res_name, "Herman Gorter")
        self.assertEqual(records[2].res_name, "Nikolay Chernyshevsky")

    def test_wildcard_search(self):
        """Test search on partial content."""
        # Should not find record without wildcard
        records = self.content_model.search([("content_tsvector", "like", "strugg")])
        self.assertFalse(records)
        records = self.content_model.search([("content_tsvector", "like", "strugg*")])
        self.assertTrue(records)
        self.assertEqual(records[0].name, "PLSR motto")

    def test_proxy_search_single_insert(self):
        """_proxy_search should use a single INSERT...SELECT, not batched ORM create().
        Verifies that:
        1. Results are correct (same records found as before).
        2. Exactly one INSERT statement is executed against fts_proxy.
        3. The date comes from the record's own date field, not create_date
           (via _proxy_search_select_expressions override in FtsContent).
        """
        proxy_model = self.env["fts.proxy"]
        domain = [
            ("res_model", "=", "fts.content"),
            ("searchstring", "like", "flame or rights"),
        ]
        insert_count = 0
        original_execute = self.env.cr.execute

        def counting_execute(query, params=None):
            nonlocal insert_count
            query_str = query.code if hasattr(query, "code") else query
            if "INSERT INTO" in query_str and "fts_proxy" in query_str:
                insert_count += 1
            return original_execute(query, params)

        self.env.cr.execute = counting_execute
        records = proxy_model.search(domain)
        self.env.cr.execute = original_execute

        # Correct results
        self.assertTrue(records)
        self.assertEqual(len(records), 2)
        for record in records:
            self.assertIn(record.res_name, ("Nikolay Chernyshevsky", "PLSR motto"))
        # Single insert
        self.assertEqual(
            insert_count,
            1,
            f"Expected 1 INSERT into fts_proxy, got {insert_count}. "
            "The INSERT...SELECT optimisation may not be active.",
        )

        # Date comes from the record's own date field, not create_date
        # (FtsContent overrides _proxy_search_select_expressions for this)
        for record in records:
            source = self.content_model.search([("name", "=", record.res_name)])
            self.assertEqual(
                record.date,
                source.date,
                f"Proxy date for '{record.res_name}' should match the record's "
                f"own date field, not create_date.",
            )
