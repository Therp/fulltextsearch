# Copyright 2024 Therp BV <https://therp.nl>.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import fields, models


class FtsProxy(models.TransientModel):

    _inherit = "fts.proxy"

    res_model = fields.Selection(
        selection_add=[("ir.attachment", "Attachments")],  # Register for FT Search
        ondelete={"ir.attachment": "cascade"},
    )

    def action_open_document(self):
        """Open related document."""
        self.ensure_one()
        result = super().action_open_document()
        if self.res_model == "ir.attachment":
            attachment_form_view = self.env.ref("fts_document.view_attachment_form_fts")
            result["views"] = [(attachment_form_view.id, "form")]
        return result
