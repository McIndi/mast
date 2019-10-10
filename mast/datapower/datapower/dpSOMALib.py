# This file is part of McIndi's Automated Solutions Tool (MAST).
#
# MAST is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3
# as published by the Free Software Foundation.
#
# MAST is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with MAST.  If not, see <https://www.gnu.org/licenses/>.
#
# Copyright 2015-2019, McIndi Solutions, All rights reserved.

from .WSClientLib import Request, etree

if hasattr(etree, 'register_namespace'):
    etree.register_namespace(
        'man',
        'http://www.datapower.com/schemas/management')
    etree.register_namespace(
        'soapenv',
        'http://schemas.xmlsoap.org/soap/envelope/')
else:
    pass
    
nsmap = {
    'soapenv': 'http://schemas.xmlsoap.org/soap/envelope/',
    'man': 'http://www.datapower.com/schemas/management',
}


class SomaRequest(Request):
    @property
    def request(self):
        return self._pointers['request']

    def clear(self):
        for node in self.request:
            self.request.remove(node)


def add_child_prep(self, tag):
    return tag.replace('_', '-')

etree.Element.add_child_prep = add_child_prep


if __name__ == '__main__':
    pass
