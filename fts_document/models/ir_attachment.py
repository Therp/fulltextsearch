# Copyright 2012-2025 Therp BV <https://therp.nl>.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import re

from odoo import api, models
from odoo.osv.expression import AND

from odoo.addons.fts_base.tsvector_field import TSVector

INDEX_CONTENT_TSVECTOR = """\
 CASE
 WHEN SUBSTRING(mimetype, 1, 5) = 'image' THEN NULL
 WHEN mimetype = 'application/javascript' THEN NULL
 WHEN mimetype = 'text/scss' THEN NULL
 WHEN mimetype = 'text/css' THEN NULL
 ELSE SUBSTRING(
 (
     COALESCE(name, ''::character varying)::text
     || ' '::text
     || COALESCE(index_content, ''::text)
 ), 1, 512 * 1024)
 END
"""


class IrAttachment(models.Model):

    _name = "ir.attachment"
    _inherit = ["ir.attachment", "fts.mixin"]

    _proxy_search_field = "content_tsvector"
    _extra_columns = ["mimetype"]

    def _index_content_tsvector(self):
        """Return string that will be used to generate content_tsvector."""
        return INDEX_CONTENT_TSVECTOR

    content_tsvector = TSVector(
        indexed_columns="_index_content_tsvector",
        help="FT Search on content",
    )

    @api.model
    def _proxy_search(self, domain, searchstring, **kwargs):
        """Exclude internal attachments from search."""
        patched_domain = AND([domain, ["!", ("res_model", "=ilike", "ir.%")]])
        return super()._proxy_search(patched_domain, searchstring, **kwargs)

    @api.model
    def _index(self, bin_data, mimetype, checksum=None):
        """Do basic sanitization of result."""
        result = super()._index(bin_data, mimetype, checksum=checksum)
        if result:
            result = re.sub(" {2,}", " ", result.strip())  # Remove extra spaces.
            result = re.sub("\n{3,}", "\n\n", result)  # Allow one blank line.
        return result
