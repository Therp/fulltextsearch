# Copyright 2024 Therp BV <https://therp.nl>.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import logging

from odoo import api, fields, models
from odoo.osv.expression import is_leaf
from odoo.tools.sql import SQL

_logger = logging.getLogger(__name__)


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
    def _search(self, domain, offset=0, limit=None, order=None):
        """Searches on tsvector fields will be done with FT Search.

        In 18 _search always returns a Query object .
        The result will be used to create proxy
        records whose ids are returned by fts.proxy._search.
        """
        # Split domain in normal parts and FT leaves.
        query_helper = self.env["fts.query.helper"]
        domain = self._replace_res_name(domain)
        fulltext_leaves, patched_domain = query_helper.fts_patch_domain(self, domain)
        if not fulltext_leaves:
            return super()._search(domain, offset=offset, limit=limit, order=order)
        return self._search_with_fulltext(
            patched_domain,
            fulltext_leaves,
            offset=offset,
            limit=limit,
            order=order,
        )

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

    def _search_with_fulltext(
        self, patched_domain, fulltext_leaves, offset=0, limit=None, order=None
    ):
        """We now know we have to process the fulltext search."""
        # This is a Query object by default
        query = super()._search(patched_domain, offset=offset, limit=limit, order=order)
        self._fts_modify_query(query, fulltext_leaves)
        select_sql = query.select()
        self.env["fts.debug.helper"].log_message(
            "SQL: %(sql)s, params=%(params)s",
            {
                "sql": select_sql.code,
                "params": str(select_sql.params),
            },
        )
        return query

    def _fts_modify_query(self, query, fulltext_leaves):
        """Replace ORM-generated equality clauses with @@ FT-search operator.

        query._where_clauses holds SQL objects. We reconstruct
        each clause by substituting the string representation, then re-wrap it
        as a raw SQL object for postgress
        """
        query_helper = self.env["fts.query.helper"]
        new_clauses = []
        for clause in query._where_clauses:
            patched_code = clause.code
            patched_params = list(clause.params)
            for table_name, field_name in fulltext_leaves:
                patched_code, patched_params = query_helper.patch_where_clause_sql(
                    patched_code, patched_params, table_name, field_name
                )
            # Re-wrap as a raw SQL object
            new_clauses.append(SQL(patched_code, *patched_params))
        query._where_clauses = new_clauses

    @api.model
    def _proxy_search_select_expressions(self):
        """Return SQL expressions for the INSERT...SELECT columns.

        Subclasses can override individual expressions to customise what gets
        inserted into fts_proxy without having to rewrite _proxy_search.

        Returns a dict with keys:
          - res_name: expression for the display name column
          - date:     expression for the date column
          - extra:    expression for the extra column
        All values must be SQL objects wrapping SQL-safe expressions.
        """
        return {
            # if title column is NULL or empty, use 'record <id>'.
            "res_name": SQL(
                f"COALESCE(NULLIF({self._title_column}::text, ''), 'record ' || id::text)"
            ),
            "date": SQL("create_date::date"),
            # Multiple _extra_columns are concatenated into a single text value.
            "extra": SQL(
                " || ' ' || ".join(
                    f"COALESCE({c}::text, '')" for c in self._extra_columns
                )
            )
            if self._extra_columns
            else SQL("NULL"),
        }

    @api.model
    def _proxy_search(self, domain, searchstring, limit=None, offset=0, **_kwargs):
        """Search matching records and insert results into fts_proxy.

        Finds matching records via the GIN index and inserts them
        into fts_proxy using a single INSERT...SELECT statement.

        Column expressions (res_name, date, extra) can be customised per model
        by overriding _proxy_search_select_expressions().

        In 18 _search no longer accepts a count parameter; counting is
        handled by search_count at a higher level, so _proxy_search always
        performs the INSERT and returns the list of inserted ids.
        """
        with_summary = self.env.context.get("fts_summary", False)
        search_limit = 80 if with_summary else 1024
        query = self._search(domain, limit=search_limit, offset=0)
        # Execute the query to get matching ids.
        self.env.cr.execute(query.select())
        res = [row[0] for row in self.env.cr.fetchall()]
        if not res:
            return res
        query_helper = self.env["fts.query.helper"]
        searchstring_parsed = query_helper.parse_searchstring(searchstring)
        now = fields.Datetime.now()
        uid = self.env.uid
        indexed_columns = self._fields[
            self._proxy_search_field
        ].get_indexed_columns_definition(self)
        exprs = self._proxy_search_select_expressions()
        # Flush pending ORM writes before raw SQL reads the source table,
        # so that e.g. a write() before search sees up-to-date column values.
        self.flush_model()
        if with_summary:
            # Wrap ts_headline in regexp_replace to normalise whitespace —
            # multi-line content (HTML bodies, documents) would otherwise
            # produce raw newlines in the UI.
            summary_sql = SQL(
                "regexp_replace(ts_headline('simple', %s,"
                " to_tsquery('simple', %s),"
                " 'StartSel = *, StopSel = *'), '\\s+', ' ', 'g')",
                SQL(indexed_columns),
                searchstring_parsed,
            )
        else:
            summary_sql = SQL("NULL")
        # Single INSERT...SELECT keeps all data inside Postgres.
        # RETURNING id gives us exactly the ids inserted by this call,
        # avoiding duplicates when searching across multiple models.
        self.env.cr.execute(
            SQL(
                """
            INSERT INTO fts_proxy
                (create_date, create_uid, write_date, write_uid,
                 res_model, res_id, rank, res_name, date, summary, extra)
            SELECT
                %s, %s, %s, %s,
                %s,
                id,
                ts_rank(%s, to_tsquery('simple', %s)),
                %s,
                %s,
                %s,
                %s
            FROM %s
            WHERE id IN %s
            RETURNING id
            """,
                now,
                uid,
                now,
                uid,
                self._name,
                SQL(self._proxy_search_field),
                searchstring_parsed,
                exprs["res_name"],
                exprs["date"],
                summary_sql,
                exprs["extra"],
                SQL(self._table),
                tuple(res),
            )
        )
        inserted_ids = [row[0] for row in self.env.cr.fetchall()]
        # Invalidate ORM cache so no stale fts.proxy records survive the INSERT.
        self.env["fts.proxy"].invalidate_model()
        return inserted_ids
