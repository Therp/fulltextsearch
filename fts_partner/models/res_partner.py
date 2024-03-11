# Copyright 2024 Therp BV <https://therp.nl>.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import models

from odoo.addons.fts_base.tsvector_field import TSVector


class ResPartner(models.Model):

    _name = "res.partner"
    _inherit = ["res.partner", "fts.mixin"]

    _proxy_search_field = "text_ts_vector"
    _title_column = "display_name"

    text_ts_vector = TSVector(
        indexed_columns=[
            "name",
            "city",
            "street",
            "street2",
            "mobile",
            "phone",
            "comment",
        ],
        help="Lexemes derived from indexed columns",
    )
