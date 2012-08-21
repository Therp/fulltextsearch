# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    This module copyright (C) 2012 Therp BV (<http://therp.nl>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
try:
    from openerp import SUPERUSER_ID
except:
    SUPERUSER_ID = 1

class fts_base_meta(type):

    _plugins = []

    def __init__(self, name, bases, attrs):
        if name != 'fts_base':

            cr = self.pool.db.cursor()
            self._plugins.append(self(self.pool, cr))
            cr.commit()
            cr.close()

        super(fts_base_meta, self).__init__(name, bases, attrs)

class fts_base(object):
    """This is the base class for modules implementing fulltext searches.
    If you want to mess around with ORM functions, you probably want to go to
    fts_proxy
    
    To define your own search operator, 
    """

    __metaclass__ = fts_base_meta

    _model = None
    """The model this search works on. Required."""

    _indexed_column = None
    """The column this search works on. Required.
    If this is a list of strings, all of them will be indexed for the fulltext
    search.
    """

    _table = None
    """The table this search works on. Will be deduced from model if
    not set."""

    _tsvector_column = None
    """The column holding tsvector data. Will be created on init.
    If not set, it will be ${_indexed_column}_tsvector."""

    _tsvector_column_index = None
    """The name of the index for _tsvector_column.
    If not set, it will be ${_indexed_column}_idx."""

    _tsvector_column_trigger = None
    """The name of the trigger to update _tsvector_column when _indexed_column
    is updated.
    If not set, it will be ${_indexed_column}_trigger."""

    _tsconfig = 'pg_catalog.simple'
    """The fulltext config (=language) to be used. Will be read from 
    properties if they exist: A specific one for the current module, then
    fts_base."""

    _title_column = 'name'
    """The column to be shown as title of a match. This can be an arbitrary SQL
    expression"""

    _disable_seqscan = True
    """The postgresql query planner (as of 9.0) chooses against using the query
    planner way too often. This forces hin to use it which improves speed in all
    tested cases. Disable (and report) if this causes problems for you."""

    def __init__(self, pool, cr):
        """Assign default values and create _tsvector_column if necessary."""
        if not self._table:
            self._table = pool.get(self._model)._table

        if not self._tsvector_column:
            self._tsvector_column = (self._indexed_column
                        if isinstance(self._indexed_column, str)
                        else '_'.join(self._indexed_column)) + '_tsvector'

        if not self._tsvector_column_index:
            self._tsvector_column_index = self._tsvector_column + '_idx'

        if not self._tsvector_column_trigger:
            self._tsvector_column_trigger = self._tsvector_column + '_trigger'

        self._create_tsvector_column(pool, cr)

    def _create_tsvector_column(self, pool, cr):
        """Create the column to hold tsvector data."""

        if (self._model is None or self._tsvector_column is None or
            self._column_exists(cr, self._table, self._tsvector_column)):
            return

        cr.execute('''
            ALTER TABLE "%(table)s" ADD COLUMN "%(tsvector_column)s"
            tsvector''' %
            {
             'tsvector_column': self._tsvector_column,
             'table': self._table,
            })

        self._create_tsvector_column_index(pool, cr)
        self._create_indexed_column_trigger(pool, cr)
        pool.get('fts.proxy').create_init_tsvector_cronjob(cr, SUPERUSER_ID,
                                                           self)

    def _create_tsvector_column_index(self, pool, cr):
        """Create an index on _tsvector_column.
        Override if you want something else than gin."""

        cr.execute('''
            CREATE INDEX "%(tsvector_column_index)s" ON "%(table)s" USING
            gin("%(tsvector_column)s")''' %
            {
             'tsvector_column_index': self._tsvector_column_index,
             'tsvector_column': self._tsvector_column,
             'table': self._table,
            })


    def _create_indexed_column_trigger(self, pool, cr):
        """Create a trigger for changes to _indexed_column"""

        cr.execute('''
            CREATE TRIGGER "%(tsvector_column_trigger)s" BEFORE INSERT OR UPDATE
            ON "%(table)s" FOR EACH ROW EXECUTE PROCEDURE
            tsvector_update_trigger("%(tsvector_column)s", '%(language)s',
            "%(indexed_column)s")''' %
            {
                'tsvector_column': self._tsvector_column,
                'tsvector_column_trigger': self._tsvector_column_trigger,
                'table': self._table,
                'language': self._tsconfig,
                'indexed_column': (self._indexed_column
                                   if isinstance(self._indexed_column, str)
                                   else '","'.join(self._indexed_column))
            })

    def _init_tsvector_column(self, pool, cr):
        """Fill _tsvector_column. This can take a long time and is called in a
        cronjob.
        Override if you want to have more than just one column indexed. In that
        case you probably also have to override
        _create_indexed_column_trigger"""

        cr.execute('''
            UPDATE "%(table)s" SET "%(tsvector_column)s"=
            to_tsvector('%(language)s', %(indexed_column)s)''' %
            {
             'tsvector_column': self._tsvector_column,
             'table': self._table,
             'language': self._tsconfig,
             'indexed_column': ('"' + self._indexed_column + '"'
                                if isinstance(self._indexed_column, str)
                                else reduce(lambda x, y: ('' if x is None else
                                                          (x + " || ' ' || ")
                                                         ) +
                                            "coalesce(\"" + y + "\", '')",
                                            self._indexed_column)),
            })

    def _column_exists(self, cr, table, column):
        """Check if a columns exists in a table"""

        cr.execute("""SELECT column_name
            FROM information_schema.columns
            WHERE table_name='%(table)s' and column_name='%(column)s'""" %
            {'table': table, 'column': column})
        return cr.rowcount == 1


    def search(self, cr, uid, args, order=None, context=None, count=False,
               searchstring=None):
        """The actual search function. Create fts.proxy objects and returns
        their ids.
        Override if you need more than full text matching against the query
        string"""

        res = []
        proxy_obj = self.pool.get('fts.proxy')

        if self._disable_seqscan:
            cr.execute('set enable_seqscan=off')

        cr.execute(
        (
            "SELECT " +
            (
            "count(*)" if count else
            """
            id,
            ts_rank(%(tsvector_column)s,
                plainto_tsquery('%(language)s', %%(searchstring)s)),
            %(title_column)s,
            """ +
                (
                """
                ts_headline('%(language)s', %(indexed_column)s,  
                    plainto_tsquery('%(language)s', %%(searchstring)s),
                    'StartSel = *, StopSel = *')"""
                if context.get('fts_summary')
                else 'null'
                )
            ) +
            """
            FROM %(table)s WHERE %(tsvector_column)s @@ 
                plainto_tsquery('%(language)s', %%(searchstring)s)"""
        ) %
        {
               'tsvector_column': self._tsvector_column,
               'table': self._table,
               'language': self._tsconfig,
               'indexed_column': ('"' + self._indexed_column + '"'
                                if isinstance(self._indexed_column, str)
                                else reduce(lambda x, y: ('' if x is None else
                                                          (x + " || ' ' || ")
                                                         ) +
                                            "coalesce(\"" + y + "\", '')",
                                            self._indexed_column)),
               'title_column': self._title_column,
        },
        {'searchstring': searchstring})

        for row in cr.fetchall():

            if count:
                return row[0]

            res.append(proxy_obj.create(cr, uid,
                                   {
                                    'model': self._model,
                                    'res_id': row[0],
                                    'rank': row[1],
                                    'name': row[2],
                                    'summary': row[3],
                                   }))

        if self._disable_seqscan:
            cr.execute('set enable_seqscan=on')

        return res