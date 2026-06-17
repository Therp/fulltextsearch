# Copyright 2025 Therp BV <https://therp.nl>.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import api, fields, models
from odoo.tools.sql import SQL

from ..tsvector_field import TSVector


class FtsContent(models.Model):
    """For the moment used for testing.

    This model might become the central repository for all indexed
    content.
    """

    _name = "fts.content"
    _inherit = ["fts.mixin"]
    _description = "Content used for testing Full Text Search"
    _order = "date DESC"
    _proxy_search_field = "content_tsvector"

    name = fields.Char("Resource Name", required=True)
    date = fields.Date(required=True)
    content = fields.Text("Content to index", required=True)
    content_tsvector = TSVector(
        indexed_columns=[
            "name",
            "content",
        ],
        help="FT Search on content",
    )

    @api.model
    def _proxy_search_select_expressions(self):
        exprs = super()._proxy_search_select_expressions()
        exprs["date"] = SQL("date")
        return exprs
