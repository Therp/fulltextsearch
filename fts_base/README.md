# fts_base

Base to add FullText Search to Odoo models.

## Breaking changes

### 16.0.1.1.0

The method `_get_fts_proxy_values()` has been removed. It was previously called by
`_proxy_search()` to build the values inserted into `fts_proxy`, but is no longer used
since `_proxy_search()` now uses a single `INSERT...SELECT` statement instead of batched
ORM `create()` calls.

If you have a custom module that overrides `_get_fts_proxy_values()`, that override will
silently have no effect after this update. Migrate your customisation to
`_proxy_search_select_expressions()` instead.
