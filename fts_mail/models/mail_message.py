# Copyright 2012-2024 Therp BV <https://therp.nl>.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import models

from odoo.addons.fts_base.tsvector_field import TSVector


class MailMessage(models.Model):

    _name = "mail.message"
    _inherit = ["mail.message", "fts.mixin"]
    _title_column = "subject"

    _proxy_search_field = "body_tsvector"

    body_tsvector = TSVector(
        indexed_columns=[
            "body",
        ],
        help="FT Search on content",
    )
