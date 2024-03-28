# Copyright 2024 Therp BV <https://therp.nl>.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import shlex

from odoo import models


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
