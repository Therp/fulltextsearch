# Copyright 2012-2025 Therp BV <https://therp.nl>.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import models

from odoo.addons.fts_base.tsvector_field import TSVector

INDEX_CONTENT_TSVECTOR = "SUBSTRING(COALESCE(body, ''::text), 1, 512 * 1024)"


class MailMessage(models.Model):

    _name = "mail.message"
    _inherit = ["mail.message", "fts.mixin"]
    _title_column = "subject"
    _extra_columns = ["email_from"]

    _proxy_search_field = "body_tsvector"

    body_tsvector = TSVector(
        indexed_columns=INDEX_CONTENT_TSVECTOR,
        help="FT Search on content",
    )
