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
        # Split domain in normal parts and FT leaves.
        (patched_domain, fulltext_leaves) = self._analyze_domain(domain)
        if not fulltext_leaves:
            return super()._search(domain, **kwargs)
        self._log_patch_message(domain, patched_domain, fulltext_leaves, **kwargs)
        return self._search_with_fulltext(patched_domain, fulltext_leaves, **kwargs)

    def _log_patch_message(self, domain, patched_domain, fulltext_leaves, **kwargs):
        """Log message to debug any problems with fulltext search."""
        self.env["fts.debug.helper"].log_message(
            "%(model)s._analyze_domain returns:"
            " domain=%(domain)s,"
            " kwargs=%(kwargs)s,"
            " patched_domain=%(patched_domain)s,"
            " fulltext_leaves=%(fulltext_leaves)s",
            {
                "model": self._name,
                "domain": str(domain),
                "kwargs": str(kwargs),
                "patched_domain": str(patched_domain),
                "fulltext_leaves": str(fulltext_leaves),
            },
        )

    def _search_with_fulltext(self, patched_domain, fulltext_leaves, **kwargs):
        """We now know we have to process the fulltext search."""
        count = kwargs.pop("count", False)  # Ensure we get Query object from super()
        query = super()._search(patched_domain, **kwargs)
        query_helper = self.env["fts.query.helper"]
        for fieldname, searchstring in fulltext_leaves.items():
            searchstring = query_helper.parse_searchstring(searchstring)
            query.add_where(
                """"%s" @@ to_tsquery('simple', %%s)""" % fieldname,
                where_params=[searchstring],
            )
        from_clause, where_clause, params = query.get_sql()
        self.env["fts.debug.helper"].log_message(
            "SQL: from=%(from_clause)s, where=%(where_clause)s, params=%(params)s",
            {
                "from_clause": str(from_clause),
                "where_clause": str(where_clause),
                "params": str(params),
            },
        )
        if count:
            limit = kwargs.get("limit", None)
            return self._handle_count(query, limit)
        # Push searchstring specs in kwargs as dirty trick to return that info.
        if self._proxy_search_field in fulltext_leaves:
            kwargs["searchstring"] = fulltext_leaves[self._proxy_search_field]
        # Return patched query.
        return query

    def _analyze_domain(self, domain):
        """Check for search on tsvector fields, and set them apart from rest."""
        patched_domain = []
        fulltext_leaves = {}  # will be keyed on fieldname.
        or_counter = 0
        for part in domain:
            if not is_leaf(part):
                if part == "|":
                    or_counter += 1
            else:
                part = self._handle_leave_part(part, or_counter, fulltext_leaves)
                if or_counter and or_counter > 0:
                    or_counter -= 1
            patched_domain.append(part)
        if not fulltext_leaves:
            # Just return original domain, and empty fulltext_leaves.
            return (domain, fulltext_leaves)
        patched_domain = self._clean_domain(patched_domain)
        return (patched_domain, fulltext_leaves)

    def _handle_leave_part(self, part, or_counter, fulltext_leaves):
        """Handle parts that contain tsvector field."""
        fieldname = self._proxy_search_field if part[0] == "searchstring" else part[0]
        if fieldname not in self._fields:
            # For the moment only support FT search in own fields.
            return part
        field = self._fields[fieldname]
        if not field.column_type or field.column_type[0] != "tsvector":
            # Not all fields, for instance Many2many, have column_type.
            return part
        prefix = (
            fulltext_leaves[fieldname] + " " if fieldname in fulltext_leaves else ""
        )
        if or_counter > 0:
            fulltext_leaves[fieldname] = prefix + part[2] + " or"
        else:
            if " or " in prefix and not prefix.endswith(" or "):
                # Group or's together.
                prefix = "(" + prefix.strip() + ") "
            fulltext_leaves[fieldname] = prefix + part[2]
        return TRUE_LEAF

    def _clean_domain(self, domain):
        """Remove some of the TRUE_LEAF's.

        They could all be eliminated, but to complicated for now.
        ."""
        if not domain or domain == [TRUE_LEAF]:
            return []
        cleaned_domain = domain.copy()
        current_index = 0
        # Precondition: we have a valid domain.
        # Stop condition: index > length of domain to return.
        # Post condition, domain contains no longer combinations of
        #    "&" or "|" followed by two TRUE_LEAF's.
        while current_index < len(cleaned_domain):
            current_first = cleaned_domain[current_index]
            head = cleaned_domain.copy()[:current_index] if current_index > 0 else []
            if current_first in ("|", "&"):
                current_next = cleaned_domain[current_index + 1]
                current_after = cleaned_domain[current_index + 2]
                if (current_next == TRUE_LEAF and current_after == TRUE_LEAF) or (
                    current_first == "&" and current_next == TRUE_LEAF
                ):
                    # Replace with single TRUE LEAVE.
                    tail = cleaned_domain.copy()[current_index + 2 :]
                    cleaned_domain = head + tail
                    current_index = 0  # Test the modified domain from the start
            current_index += 1
            # The stop condition will always be reached, because either we increase
            # the index, or we decrease the length of the domain to return. Though
            # we reset the index to zero on replacing a combination with a single
            # TRUE_LEAVE, in the end there will be no more combinations, and the
            # index will then keep on incrementing.
        return cleaned_domain

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
    def _proxy_search(self, domain, **kwargs):
        """Search first, then create proxy records."""
        count = kwargs.get("count", False)
        new_kwargs = dict(kwargs)
        new_kwargs["limit"] = 1024  # Search further...
        new_kwargs["offset"] = 0  # Search further...
        res = self._search(domain, **new_kwargs)
        if count or not res:
            return res
        query_helper = self.env["fts.query.helper"]
        searchstring = query_helper.parse_searchstring(kwargs.pop("searchstring", ""))
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
