
Introduction
------------

Provides an extensible framework for Odoo to do full text search, using PostgreSQL's
full text search mechanism, on different models. It aims at least possible administration
effort while still providing fast and high quality search results for users. The modular
design enables administrators to offer just the full text search wanted and developers
an easy way to add searches.

For Odoo 16.0 this has been significantly overhauled from the original OpenERP 6.1 / 7.0
implementation, using features that have since been added to PostgreSQL.

The original implementation was presented here:
[Open Days 2013](http://www.slideshare.net/openobject/using-full-text-search-in-open-erpholger-brunntherp-ready-partner)

Administrators
--------------

* Install the search module you are interested in (ie `fts_document` to search in
  attachments), Installation might take some time, as existing rows in the
  database will be indexed.

Developers
----------

* Add the ftx\_mixin to your inheritance, for instance like this:
  ```
  class IrAttachment(models.Model):

    _name = "ir.attachment"
    _inherit = ["ir.attachment", "fts.mixin"]
  ```
* Set the class attributes \_proxy\_search\_field and \_extra\_columns:

    _proxy_search_field = "content_tsvector"
    _extra_columns = ["mimetype"]

* Import tthe TSVectorField field definition and add one or more fields:
  (the main search field must be set in the \_proxy\_search\_field attribute)
  ```
    from odoo.addons.fts_base.tsvector_field import TSVector
    ...
        content_tsvector = TSVector(
        indexed_columns=[
            "index_content",
        ],
        help="FT Search on content",
  ```
  It is possible to have multiple TSVector fields and search on them
  (add them to your search fields).

* If you want to include your model in the global search over all
  supported models, override the fts\_proxy model to add your model,
  and update the fts\_proxy search view.
  ```
  class FtsProxy(models.TransientModel):

    _inherit = "fts.proxy"

    res_model = fields.Selection(
        selection_add=[("ir.attachment", "Attachments")],  # Register for FT Search
        ondelete={"ir.attachment": "cascade"},
    )
  ```
* Share your results.

Support
-------

For commercial support, please contact [Therp BV](http://therp.nl).
