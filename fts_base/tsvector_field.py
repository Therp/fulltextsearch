# Copyright 2024 Therp BV <https://therp.nl>.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import logging

from psycopg2.extensions import AsIs

from odoo.fields import Field

_schema = logging.getLogger("odoo.schema")

CREATE_TSVECTOR_COLUMN = (
    "ALTER TABLE %(table_name)s ADD COLUMN %(column_name)s tsvector"
    " GENERATED ALWAYS AS (to_tsvector('simple', %(indexed_columns)s)) STORED"
)
CHECK_TSVECTOR_COLUMN = (
    "SELECT attgenerated FROM pg_attribute"
    " WHERE attrelid = '%(table_name)s'::regclass AND attname = '%(column_name)s' "
)
DROP_TSVECTOR_COLUMN = "ALTER TABLE %(table_name)s DROP COLUMN %(column_name)s"
CREATE_TSVECTOR_INDEX = (
    "CREATE INDEX %(table_name)s_%(column_name)s_index"
    " ON %(table_name)s USING GIN(%(column_name)s)"
)


class TSVector(Field):
    """Define field of tsvector type."""

    type = "tsvector"
    column_type = ("tsvector", "tsvector")
    readonly = True
    copy = False

    def update_db_column(self, model, column):
        """Create/update the column corresponding to ``self``.

        :param model: an instance of the field's model
        :param column: the column's configuration (dict) if it exists, or ``None``
        """
        param_dict = {
            "table_name": AsIs(model._table),
            "column_name": AsIs(self.name),
            "indexed_columns": AsIs(self.get_indexed_columns_definition(model)),
        }
        if column and column["udt_name"] == "tsvector":
            # When column created together with table, it will miss the
            # GENERATED AS... part. In that case, also need to drop the
            # column and create it afresh.
            model._cr.execute(CHECK_TSVECTOR_COLUMN, param_dict)
            attgenerated = model._cr.fetchone() if model._cr.rowcount else ""
            if attgenerated and attgenerated[0] == "s":
                # Column is generated, assume with the right definition.
                return
        if column:  # Column exist, but is of wrong type.
            # Drop column to recreate it.
            param_dict["udt_name"] = column["udt_name"]
            model._cr.execute(DROP_TSVECTOR_COLUMN, param_dict)
            _schema.debug(
                "Table %(table_name)s:"
                " dropped column %(column_name)s of type %(udt_name)s",
                param_dict,
            )
            column = None
        if not column:
            # the column does not exist, create it
            model._cr.execute(CREATE_TSVECTOR_COLUMN, param_dict)
            _schema.debug(
                "Table %(table_name)s: added column %(column_name)s of type tsvector",
                param_dict,
            )
        # Now create index on column.
        model._cr.execute(CREATE_TSVECTOR_INDEX, param_dict)

    def get_indexed_columns_definition(self, model):
        """Get formula to generate content for indexed columns"""
        indexed_columns = self.indexed_columns
        if isinstance(indexed_columns, str):
            if hasattr(model, indexed_columns):
                return getattr(model, indexed_columns)()  # Call model method.
            return "COALESCE(%s, '')" % indexed_columns  # Single column
        # We need the COALESCE to prevent problems with NULL values in indexed fields.
        return " || ' ' || ".join(
            ["COALESCE(%s, '')" % fieldname for fieldname in indexed_columns]
        )
