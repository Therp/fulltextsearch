# Copyright 2024 Therp BV <https://therp.nl>.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import shlex

from odoo import _, models
from odoo.exceptions import UserError
from odoo.osv.expression import FALSE_LEAF, TRUE_LEAF, is_leaf


class FtsQueryHelper(models.AbstractModel):
    """Provides functions to assist in FT Search.

    Define as AbstractModel for easy extention and being able
    to load this through the registry.
    """

    _name = "fts.query.helper"
    _description = __doc__

    def parse_searchstring(self, searchstring):
        """Convert entered searchstring to to_tsquery compatible format.

        This function does a lot of things webqsearch_to_tsquery does,
        but that does not support substring searches (with 'sometext:*').

        What the function does:
            - Change quoted strings to <->:  "bla text" -> bla<->text;
            - And multiple words: bla text -> bla & text;
            - Properly format substrings: bla* -> bla:*;
            - Change tekstual operators into symbols: bla or text -> bla | text.
        """
        parsed_string = " & ".join(
            [
                "<->".join(part.split())  # Join adjacent words in quoted string.
                # Splitting with shlex keeps quoted strings together.
                for part in shlex.split(
                    searchstring.lower().replace(" and ", " & ").replace(" or ", " | ")
                )
                if part != "&"  # Will be added back later if needed.
            ]
        )
        # TODO: Find nicer solution with regular expressions...
        parsed_string = (
            parsed_string.replace("*", ":*")
            .replace("::", ":")
            .replace(" & | & ", " | ")
        )
        return parsed_string

    def patch_where_clause_sql(self, code, params, table_name, field_name):
        """Replace an equals (=) selection with a FT search selection.

        Works on the raw SQL code string and params list extracted from an
        Odoo 18 SQL object (where _where_clauses stores SQL instances).

        "<table_name>"."<field_name>"::text = %s  ==>
        "<table_name>"."<field_name>" @@ to_tsquery('simple', %s)

        There might be a '::text' cast after the field name; both variants
        are handled.
        """
        needle_cast = f'"{table_name}"."{field_name}"::text = %s'
        needle_plain = f'"{table_name}"."{field_name}" = %s'
        replacement = (
            f'"{table_name}"."{field_name}" @@ to_tsquery(\'simple\', %s)'
        )
        if needle_cast in code:
            code = code.replace(needle_cast, replacement)
        elif needle_plain in code:
            code = code.replace(needle_plain, replacement)
        return code, params

    def get_model_and_field(self, start_model, dotted_field_name):
        """Get model and field for dotted_field_name."""
        DOT = "."
        if DOT not in dotted_field_name:
            return (start_model, dotted_field_name)
        parts = dotted_field_name.split(DOT, 1)
        field_name = parts[0]
        if not start_model._fields[parts[0]].comodel_name:
            raise UserError(
                _(
                    "Field %(field_name)s in model %(model_name)s"
                    " is not an X2x field."
                )
                % {
                    "field_name": field_name,
                    "model_name": start_model._name,
                }
            )
        next_model = self.env[start_model._fields[parts[0]].comodel_name]
        next_field_name = parts[1]
        return self.get_model_and_field(next_model, next_field_name)

    def fts_patch_domain(self, model, domain):
        """Will find all tsvector fields in domain and replace searchstrings."""
        patched_domain = []  # Unfortunately we can not do in place substitutions.
        fulltext_leaves = []  # Might contain duplicates, to unlikely to care.
        for part in domain:
            if (not is_leaf(part)) or part in (TRUE_LEAF, FALSE_LEAF):
                patched_domain.append(part)  # append as is
                continue
            actual_name = (
                model._proxy_search_field if part[0] == "searchstring" else part[0]
            )
            field_model, field_name = self.get_model_and_field(model, actual_name)
            field = field_model._fields[field_name]
            if not field.column_type or field.column_type[0] != "tsvector":
                patched_domain.append(part)  # append as is
                continue
            patched_domain.append(
                (
                    actual_name,
                    "=",  # Use '=' to prevent default search adding '%' characters.
                    self.parse_searchstring(part[2]),
                )
            )
            fulltext_leaves.append(
                (
                    field_model._table,
                    field_name,
                )
            )
        return fulltext_leaves, patched_domain
