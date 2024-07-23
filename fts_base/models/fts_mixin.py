# Copyright 2024 Therp BV <https://therp.nl>.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import logging

from psycopg2.extensions import AsIs

from odoo import api, models
from odoo.osv.expression import TRUE_LEAF, is_leaf

_logger = logging.getLogger(__name__)

FTS_PROXY_SELECT = (
    "SELECT"
    " id"
    ", ts_rank(%(tsvector_column)s, to_tsquery(%(language)s, %(searchstring)s))"
    ", %(title_column)s"
    ", create_date"
)
FTS_PROXY_SUMMARY_SELECT = (
    ", ts_headline(%(language)s, %(indexed_columns)s,"
    "to_tsquery(%(language)s, %(searchstring)s),"
    "'StartSel = *, StopSel = *')"
)
FTS_PROXY_FROM_WHERE = "FROM %(table_name)s WHERE id IN %(ids)s"


class FtsMixin(models.AbstractModel):
    """Add this to each model that needs FullText search functions."""

    _name = "fts.mixin"
    _description = __doc__

    # For the moment we only support searching on one field per model to be
    # included in the general search interface. The field here must be a
    # ts_vector type field in this model.
    _proxy_search_field = None
    _title_column = "name"  # Will be used to set res_name in fts.proxy
    _extra_columns = []  # Add extra columns

    def _valid_field_parameter(self, field, name):
        return name == "indexed_columns" or super()._valid_field_parameter(field, name)

    @api.model
    def _search(self, domain, **kwargs):
        """Searches on tsvector fields will be done with FT Search.

        The search can return a count or a query (returning ids) in the
        normal way, or the result will be used to create proxy records,
        and the ids of those will be returned.
        """
        query_helper = self.env["fts.query.helper"]
        # Split domain in normal parts and FT leaves.
        patched_domain = []
        fulltext_leaves = []
        non_leaves = False
        for part in domain:
            if is_leaf(part):
                if part[0] in self._fields:
                    # For the moment only support FT search in own fields.
                    field = self._fields[part[0]]
                    # Not all fields, for instance Many2many, have column_type.
                    if field.column_type and field.column_type[0] == "tsvector":
                        fulltext_leaves.append(part)
                        patched_domain.append(TRUE_LEAF)
                        continue
            else:
                non_leaves = True
            patched_domain.append(part)
        if not fulltext_leaves:
            return super()._search(domain, **kwargs)
        if non_leaves:
            _logger.debug(
                "Search on %(model)s combines non_leaves with FT search,"
                " result might not be what is expected.",
                {"model": self._name},
            )
        count = kwargs.pop("count", False)  # Ensure we get Query object from super()
        query = super()._search(patched_domain, **kwargs)
        for leave in fulltext_leaves:
            searchstring = query_helper.parse_searchstring(leave[2])
            query.add_where(
                """"%s" @@ to_tsquery('simple', %%s)""" % leave[0],
                where_params=[searchstring],
            )
        from_clause, where_clause, params = query.get_sql()
        _logger.debug(
            "SQL: from - %(from_clause)s, where - %(where_clause)s, params - %(params)s",
            {
                "from_clause": str(from_clause),
                "where_clause": str(where_clause),
                "params": str(params),
            },
        )
        if count:
            limit = kwargs.get("limit", None)
            return self._handle_count(query, limit)
        # Return patched query.
        return query

    def _handle_count(self, query, limit):
        """This part taken from original _search method."""
        # Ignore order and offset when just counting, they don't make sense and could
        # hurt performance
        if limit:
            # Special case to avoid counting every record in DB (which can be really slow).
            # The result will be between 0 and limit.
            query_str, params = query.select("")  # generates a `SELECT FROM` (faster)
            query_str = f"SELECT COUNT(*) FROM ({query_str}) t"
        else:
            query_str, params = query.select("COUNT(*)")
        self._cr.execute(query_str, params)
        return self._cr.fetchone()[0]

    @api.model
    def _proxy_search(self, searchstring, domain, **kwargs):
        """Search first, then create proxy records."""
        count = kwargs.get("count", False)
        new_kwargs = dict(kwargs)
        new_kwargs["limit"] = 1024  # Search further...
        new_kwargs["offset"] = 0  # Search further...
        res = self._search(domain, **new_kwargs)
        if count or not res:
            return res
        query_helper = self.env["fts.query.helper"]
        searchstring = query_helper.parse_searchstring(searchstring)
        indexed_columns = self._fields[
            self._proxy_search_field
        ].get_indexed_columns_definition()
        params_dict = {
            "tsvector_column": AsIs(self._proxy_search_field),
            "language": "simple",
            "searchstring": searchstring,
            "title_column": AsIs(self._title_column),
            "indexed_columns": AsIs(indexed_columns),
            "table_name": AsIs(self._table),
            "ids": tuple(res),
        }
        with_summary = self.env.context.get("fts_summary", False)
        query_str = " ".join(
            [
                FTS_PROXY_SELECT,
                FTS_PROXY_SUMMARY_SELECT if with_summary else ", NULL",
                ", %s" % ", ".join(self._extra_columns) if self._extra_columns else "",
                FTS_PROXY_FROM_WHERE,
            ]
        )
        self._cr.execute(query_str, params_dict)
        rows = self._cr.fetchall()
        vals_list = []
        for row in rows:
            vals = self._get_fts_proxy_values(row)
            vals_list.append(vals)
        proxy_model = self.env["fts.proxy"]
        return proxy_model.create(vals_list).ids

    @api.model
    def _get_fts_proxy_values(self, row):
        """Get vals to fill proxy."""
        # rank = min(100, row[0] * 1000)
        rank = row[0]
        summary = str(row[4]) if row[4] else ""
        if summary:
            # Get rid of duplicate whitespace and new lines.
            summary = " ".join(summary.split())
        return {
            "res_model": self._name,
            "res_id": row[0],
            "rank": rank,
            "res_name": row[2],
            "date": row[3],
            "summary": summary,
            "extra": False if len(row) <= 5 else row[5],
        }
