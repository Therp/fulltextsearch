# Copyright 2024 Therp BV <https://therp.nl>.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import logging

from odoo import api, fields, models, registry
from odoo.osv.expression import AND, is_leaf

_logger = logging.getLogger(__name__)


class FtsProxy(models.TransientModel):
    """Front end to show results of FT searches, together with rank and summary."""

    _name = "fts.proxy"
    _description = __doc__
    _rec_name = "res_name"
    _order = "date DESC, rank DESC"

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
    date = fields.Date()
    extra = fields.Char()
    searchstring = fields.Char(
        compute=lambda self: None,
        search="_search_searchstring",
    )

    @api.model
    def _search(self, domain, **kwargs):
        """Searches in some or all models."""
        # Always remove any existing records. Use SQL as unlink does not
        # delete al the records that need deleting.
        with registry(self.env.cr.dbname).cursor() as new_cursor:
            new_cursor.execute(
                "DELETE FROM fts_proxy WHERE create_uid = %s", (self.env.uid,)
            )
            new_cursor.commit()
        self.invalidate_model()  # Clear all caches for this model.
        # For all models, create transient record, then return all ids.
        (searchstring, new_domain, models) = self._analyze_domain(domain, **kwargs)
        count = kwargs.get("count", False)
        res = 0 if count else []
        # If no search criteria, return Nothing (reversing normal result).
        if not searchstring:
            _logger.debug("doing nothing because I got no search string")
            return res
        if not models:  # Should not happen, only when no additonal module installed.
            _logger.debug("doing nothing because I got no models to search")
            return res
        for model in models:
            res += self._search_model(model, searchstring, new_domain, **kwargs)
        # Return ordered results.
        return super()._search([("create_uid", "=", self.env.uid)], **kwargs)

    def _analyze_domain(self, domain, **kwargs):
        """Get searchstring, modified domain, models used, fields used."""
        searchstring = ""
        models = []
        query_fields = set()
        new_domain = []
        for part in domain:
            if is_leaf(part):
                if part[0] == "searchstring":
                    if searchstring:
                        searchstring += " " + part[2]
                    else:
                        searchstring = part[2]
                    continue
                if part[0] == "res_model":
                    models.append(part[2])
                    continue
                if part[0] == "date":
                    part[0] = "create_date"
                else:
                    # Add first (or only) part of fieldname to set.
                    query_fields.add(part[0].split(".")[0])
                new_domain.append(part)
        # If not models, search in all registered models (for all ts_vector fields)
        if not models:
            models = [selection[0] for selection in self._fields["res_model"].selection]
        # Remove model if query contains any field that is not in the model.
        models = [
            model
            for model in models
            if not self._model_missing_field(model, query_fields)
        ]
        return (searchstring, new_domain, models)

    def _model_missing_field(self, model, query_fields):
        """If domain contains field not in model, ignore model."""
        model_obj = self.env[model]
        for field_name in query_fields:
            if field_name not in model_obj._fields:
                _logger.debug(
                    "_field %(field_name)s not present on model %(model)s",
                    {
                        "model": model_obj._name,
                        "field_name": field_name,
                    },
                )
                return True
        return False

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

    def action_open_document(self):
        """Open related document."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self.res_model,
            "view_type": "form",
            "view_mode": "form,tree",
            "res_id": self.res_id,
        }
