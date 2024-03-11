# Copyright 2024 Therp BV <https://therp.nl>.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import fields, models


class FtsProxy(models.TransientModel):

    _inherit = "fts.proxy"

    res_model = fields.Selection(
        selection_add=[("ir.attachment", "Attachments")],  # Register for FT Search
        ondelete={"ir.attachment": "cascade"},
    )
