# Copyright 2024 Therp BV <https://therp.nl>.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import logging

from psycopg2.extensions import AsIs

from odoo import api, fields, models
from odoo.osv.expression import is_leaf

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
        query_helper = self.env["fts.query.helper"]
        domain = self._replace_res_name(domain)
        fulltext_leaves, patched_domain = query_helper.fts_patch_domain(self, domain)
        if not fulltext_leaves:
            return super()._search(domain, **kwargs)
        return self._search_with_fulltext(patched_domain, fulltext_leaves, **kwargs)

    def _replace_res_name(self, domain):
        """If records will be filtered on res_name, use actual name field."""
        new_domain = []
        for part in domain:
            if is_leaf(part):
                if part[0] == "res_name":
                    new_domain.append((self._title_column, part[1], part[2]))
                    continue
            new_domain.append(part)
        return new_domain

    def _search_with_fulltext(self, patched_domain, fulltext_leaves, **kwargs):
        """We now know we have to process the fulltext search."""
        count = kwargs.pop("count", False)  # Ensure we get Query object from super()
        query = super()._search(patched_domain, **kwargs)
        self._fts_modify_query(query, fulltext_leaves)
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
        # Return patched query.
        return query

    def _fts_modify_query(self, query, fulltext_leaves):
        """Where needed modify like into @@."""
        query_helper = self.env["fts.query.helper"]
        for index, clause in enumerate(query._where_clauses):
            for leave in fulltext_leaves:
                clause = query_helper.patch_where_clause(clause, leave[0], leave[1])
            query._where_clauses[index] = clause

    def _handle_count(self, query, limit):
        """This part taken from original _search method."""
        # Ignore order and offset when just counting, they don't make sense and could
        # hurt performance
        query.order = None
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
    def _proxy_search_select_expressions(self):
        """Return SQL expressions for the INSERT...SELECT columns.

        Subclasses can override individual expressions to customise what gets
        inserted into fts_proxy without having to rewrite _proxy_search.

        Returns a dict with keys:
          - res_name: expression for the display name column
          - date:     expression for the date column
          - extra:    expression for the extra column
        All values must be AsIs() instances wrapping SQL-safe expressions.
        """
        return {
            # if title column is NULL or empty, use 'record <id>'.
            "res_name": AsIs(
                f"COALESCE(NULLIF({self._title_column}::text, ''), 'record ' || id::text)"
            ),
            "date": AsIs("create_date::date"),
            # Multiple _extra_columns are concatenated into a single text value.
            # Concatenating into one column matches the single fts_proxy.extra target.
            "extra": AsIs(
                " || ' ' || ".join(
                    f"COALESCE({c}::text, '')" for c in self._extra_columns
                )
            )
            if self._extra_columns
            else AsIs("NULL"),
        }

    @api.model
    def _proxy_search(self, domain, searchstring, **kwargs):
        """Search matching records and insert results into fts_proxy.

        Finds matching records via the GIN index and inserts them
        into fts_proxy using a single INSERT...SELECT statement.

        Column expressions (res_name, date, extra) can be customised per model
        by overriding _proxy_search_select_expressions().
        """
        # Copy kwargs defensively to avoid mutating dict.
        kwargs = dict(kwargs)
        # Pop count before passing to _search — count=True returns an int,
        # not a Query, and must be short-circuited before the INSERT.
        count = kwargs.pop("count", False)
        kwargs.pop("order", False)  # Ordering will be done later.
        kwargs["limit"] = 1024
        kwargs["offset"] = 0
        res = self._search(domain, count=count, **kwargs)
        if count or not res:
            return res
        query_helper = self.env["fts.query.helper"]
        searchstring_parsed = query_helper.parse_searchstring(searchstring)
        with_summary = self.env.context.get("fts_summary", False)
        now = fields.Datetime.now()
        uid = self.env.uid

        indexed_columns = self._fields[
            self._proxy_search_field
        ].get_indexed_columns_definition(self)

        if with_summary:
            # Wrap ts_headline in regexp_replace to normalise whitespace —
            # multi-line content (HTML bodies, documents) would otherwise
            # produce raw newlines in the UI.
            summary_expr = (
                "regexp_replace(ts_headline('simple', %(indexed_columns)s,"
                " to_tsquery('simple', %(searchstring)s),"
                " 'StartSel = *, StopSel = *'), '\\s+', ' ', 'g')"
            )
        else:
            summary_expr = "NULL"

        exprs = self._proxy_search_select_expressions()
        # Flush pending ORM writes before raw SQL reads the source table,
        # so that e.g. a write() before search sees up-to-date column values.
        self.flush_model()
        # Single INSERT...SELECT keeps all data inside Postgres.
        # RETURNING id gives us exactly the ids inserted by this call,
        # avoiding duplicates when searching across multiple models.
        self._cr.execute(
            """
            INSERT INTO fts_proxy
                (create_date, create_uid, write_date, write_uid,
                 res_model, res_id, rank, res_name, date, summary, extra)
            SELECT
                %%(now)s, %%(uid)s, %%(now)s, %%(uid)s,
                %%(res_model)s,
                id,
                ts_rank(%%(tsvector_column)s,
                        to_tsquery('simple', %%(searchstring)s)),
                %%(res_name_expr)s,
                %%(date_expr)s,
                %s,
                %%(extra_expr)s
            FROM %%(table_name)s
            WHERE id IN %%(ids)s
            RETURNING id
            """
            % summary_expr,
            {
                "now": now,
                "uid": uid,
                "res_model": self._name,
                "tsvector_column": AsIs(self._proxy_search_field),
                "searchstring": searchstring_parsed,
                "indexed_columns": AsIs(indexed_columns) if with_summary else None,
                "res_name_expr": exprs["res_name"],
                "date_expr": exprs["date"],
                "extra_expr": exprs["extra"],
                "table_name": AsIs(self._table),
                "ids": tuple(res),
            },
        )
        inserted_ids = [row[0] for row in self._cr.fetchall()]
        # Invalidate ORM cache so no stale fts.proxy records survive the INSERT.
        self.env["fts.proxy"].invalidate_model()
        return inserted_ids
