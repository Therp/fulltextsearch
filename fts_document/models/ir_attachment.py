# Copyright 2012-2024 Therp BV <https://therp.nl>.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import re

from odoo import api, models
from odoo.osv.expression import AND

from odoo.addons.fts_base.tsvector_field import TSVector


class IrAttachment(models.Model):

    _name = "ir.attachment"
    _inherit = ["ir.attachment", "fts.mixin"]

    _proxy_search_field = "content_tsvector"
    _extra_columns = ["mimetype"]

    content_tsvector = TSVector(
        indexed_columns=[
            "name",
            "index_content",
        ],
        help="FT Search on content",
    )

    @api.model
    def _proxy_search(self, domain, **kwargs):
        """Exclude internal attachments from search."""
        patched_domain = AND([domain, ["!", ("res_model", "=ilike", "ir.%")]])
        return super()._proxy_search(patched_domain, **kwargs)

    @api.model
    def _index(self, bin_data, mimetype, checksum=None):
        """Do basic sanitization of result."""
        result = super()._index(bin_data, mimetype, checksum=checksum)
        if result:
            result = re.sub(" {2,}", " ", result.strip())  # Remove extra spaces.
            result = re.sub("\n{3,}", "\n\n", result)  # Allow one blank line.
        return result
