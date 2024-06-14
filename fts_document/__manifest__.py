# Copyright 2012-2024 Therp BV <https://therp.nl>.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
{
    "name": "Fulltext search - documents",
    "summary": "Add fulltext search on attachments",
    "version": "16.0.1.0.0",
    "depends": ["fts_base"],
    "website": "https://github.com/Therp/fulltextsearch",
    "author": "Therp BV",
    "license": "AGPL-3",
    "category": "Searching",
    "data": [
        "views/fts_proxy.xml",
        "views/ir_attachment.xml",
    ],
    "installable": True,
}
