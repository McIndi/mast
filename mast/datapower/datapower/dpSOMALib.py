#/usr/bin/env python

from WSClientLib import Request, etree

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
