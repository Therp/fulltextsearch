# Copyright 2024 Therp BV <https://therp.nl>.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import logging

from odoo import api, fields, models
from odoo.osv.expression import AND, is_leaf

_logger = logging.getLogger(__name__)


class FtsProxy(models.TransientModel):
    """Front end to show results of FT searches, together with rank and summary."""

    _name = "fts.proxy"
    _description = __doc__
    _rec_name = "res_name"
    _order = "rank DESC, res_model ASC"

    def _search_searchstring(self, operator, value):
        """Add searchstring to domain. Operator will be ignored."""
        return [("searchstring", "like", value)]

    res_name = fields.Char("Resource Name", readonly=True, required=True)
    res_model = fields.Selection(
        selection=[],  # Supported models should register with _selection_add.
        string="Resource Model",
        readonly=True,
        required=True,
        help="The model this search works on. Required.",
    )
    res_id = fields.Many2oneReference(
        string="Resource ID",
        model_field="res_model",
        readonly=True,
        required=True,
    )
    rank = fields.Float(string="Rank", digits=(8, 4), compute=False, readonly=True)
    summary = fields.Text("Summary", readonly=True)
    searchstring = fields.Char(
        compute=lambda self: None,
        search="_search_searchstring",
    )

    @api.model
    def _search(self, domain, **kwargs):
        """Searches in some or all models."""
        count = kwargs.pop("count", False)
        res = 0 if count else []
        # For all models, create transient record, then return all ids.
        searchstring = ""
        models = []
        new_domain = []
        for part in domain:
            if is_leaf(part):
                if part[0] == "searchstring":
                    searchstring = part[2]
                    continue
                if part[0] == "res_model":
                    models.append(part[2])
                    continue
                new_domain.append(part)
        # If no search criteria, return Nothing (reversing normal result).
        if not searchstring:
            _logger.debug("doing nothing because I got no search string")
            return res
        # If not models, search in all registered models (for all ts_vector fields)
        if not models:
            models = [selection[0] for selection in self._fields["res_model"].selection]
        if not models:
            return res
        for model in models:
            res += self._search_model(model, searchstring, new_domain, **kwargs)
        return res

    def _search_model(self, model, searchstring, domain, **kwargs):
        """FT search on all ts_vector fields in model."""
        count = kwargs.get("count", False)
        model_obj = self.env[model]
        if not model_obj._proxy_search_field:
            _logger.debug(
                "_proxy_search_field not set on model %(model)s",
                {"model": model_obj._name},
            )
            return 0 if count else []
        return model_obj.with_context(
            proxy_create=False if count else True
        )._proxy_search(
            searchstring,
            AND([domain, [(model_obj._proxy_search_field, "like", searchstring)]]),
            **kwargs
        )

    def open_document(self):
        """Open related document."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self.res_model,
            "view_type": "form",
            "view_mode": "form,tree",
            "res_id": self.res_id,
        }
