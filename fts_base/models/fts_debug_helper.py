# Copyright 2024 Therp BV <https://therp.nl>.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class FtsDebugHelper(models.AbstractModel):
    """Provides logging function to analyse FT problems.

    This class is needed to not flood the log with FTS debug
    messages, but only log stuff when actually having an Odoo
    session in debug mode.

    We will use info level messages, so this will also work
    on production servers where normally you will not have
    debug level logging.
    """

    _name = "fts.debug.helper"
    _description = __doc__

    def log_message(self, message, message_dict):
        """Log message when odoo session in debug mode."""
        if self.user_has_groups("base.group_no_one"):
            _logger.info(message, message_dict)
