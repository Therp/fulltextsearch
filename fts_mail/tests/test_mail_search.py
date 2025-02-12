# Copyright 2025 Therp BV <https://therp.nl>.
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestMailSearch(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Proxy = cls.env["fts.proxy"]
        cls.Message = cls.env["mail.message"]
        cls.Partner = cls.env["res.partner"]
        cls.partner_jan = cls.Partner.create(
            {
                "is_company": False,
                "name": "Jan Boezeroen",
                "email": "jboezeroen@example.com",
            }
        )

    def test_search_mail(self):
        """Test search posted mail."""
        self.partner_jan.message_post(
            body="Een nieuwe lente, een nieuw geluid:\n"
            "Ik wil dat dit lied klinkt als het gefluit,\n"
            "Dat ik vaak hoorde voor een zomernacht\n"
            "In een oud stadje, langs de watergracht."
        )
        records = self.Message.search([("body_tsvector", "like", "zomernacht")])
        self.assertTrue(records)
        self.assertEqual(records[0].model, self.Partner._name)
        self.assertEqual(records[0].res_id, self.partner_jan.id)
        proxy_records = self.Proxy.search(
            [
                ("res_model", "=", self.Message._name),
                ("searchstring", "=", "lente zomernacht"),
            ]
        )
        self.assertTrue(proxy_records)
        proxy = proxy_records[0]
        self.assertEqual(proxy.res_model, self.Message._name)
        message = self.Message.browse(proxy.res_id)
        self.assertEqual(message.model, self.Partner._name)
        self.assertEqual(message.res_id, self.partner_jan.id)
