Introduction
------------

Provides an extensible framework for OpenERP to do full text search (using PostgreSQL's full text search mechanism) on different models. It aims at least possible administration effort while still providing fast and high quality search results for users. The modular design enables administrators to offer just the full text search wanted and developers an easy way to add searches.

For a quick (somewhat technical) overview, read the presentation held on the [Open Days 2013](http://www.slideshare.net/openobject/using-full-text-search-in-open-erpholger-brunntherp-ready-partner)

Administrators
--------------

* Install the search module you are interested in (ie `fts_document` to search in documents)
* Watch your logs. It will fill an index in the background. Look for the line '`running _init_tsvector_column for [somename]`'
* After that finishes (depending on the size of the table some minutes to some hours), you can do your searches

Developers
----------

* Derive a class from `fts_base` in your new module
* Set at least the attributes `_model` and `_indexed_column`
* Read the comments in `fts_base`
* Most likely change the search view of fts.proxy
* Share your results

Support
-------

For commercial support, please contact [Therp BV](http://therp.nl).
