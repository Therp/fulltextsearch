# Copyright 2012-2024 Therp BV <https://therp.nl>.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import models

from odoo.addons.fts_base.tsvector_field import TSVector


class IrAttachment(models.Model):

    _name = "ir.attachment"
    _inherit = ["ir.attachment", "fts.mixin"]

    _proxy_search_field = "content_tsvector"
    _extra_columns = ["mimetype"]

    content_tsvector = TSVector(
        indexed_columns=[
            "index_content",
        ],
        help="FT Search on content",
    )
