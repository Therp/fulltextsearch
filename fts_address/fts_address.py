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
    from openerp.addons.fts_base.fts_base import fts_base
except:
    from fts_base.fts_base import fts_base

class fts_address(fts_base):

    _model = 'res.partner.address'
    _indexed_column = ['name', 'city', 'street', 'street2', 'mobile', 'phone']
    _title_column = '''
    case 
    when name is null or name = '' then 
        (select name from res_partner where id=partner_id)
    else 
        name
    end'''
