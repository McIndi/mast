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
import et.ElementTree as etree
import xml.etree.cElementTree as cEtree
import base64
import urllib2

TIMEOUT = 120


# Custom exceptions
class InvalidTestCaseFormat(Exception):
    pass


class InvalidChildError(Exception):
    pass


class InvalidAttributeError(Exception):
    pass


# Methods to be monkey-patched to etree.Element class
def get_path(self):
    """
    get_path: Public Function:
        This will attempt to build an xpath relevant to the current
        node such that tree.getroot().find(node.get_path()) == current node.
    """
    parent = ''
    path = self.tag
    sibs = self.parent.findall(self.tag)
    if len(sibs) > 1:
        path = path + '[%s]' % (sibs.index(self) + 1)
    cur_node = self
    while True:
        parent = cur_node.parent
        ptag = parent.tag
        path = ptag + '/' + path
        cur_node = parent
        if cur_node.parent.parent is None:
            break
    return path


def add_attribute(self, **kwargs):
    """
    add_attribute: Public Function:
        This is a convenience method wrapping self.owner.add_attribute.
        This will take an arbitrary number of key word arguments, loop
        through them and set the attributes of this node.
    """
    return self.owner.set_attribute(self, **kwargs)


def add_child(self, tag):
    """
    add_child: Public Function:
        This function is a convenience method for accessing
        self.owner.owner.SubElement
        Note that if you override a function called 'add_child_prep'
        then that will be called before the element is made. add_child_prep
        should take the tag name as a string and return a modified tag name
    """
    if hasattr(self, 'add_child_prep'):
        tag = self.add_child_prep(tag)
    return self.owner.SubElement(self, tag)


def valid_children(self):
    """
    valid_children:
        generator which returns the valid children of an element
    """
    for child in self.owner.valid_children(self):
        yield child


def valid_attributes(self):
    """
    valid_attributes:
        generator which returns the valid attributes of an element
    """
    for attr in self.owner.valid_attributes(self):
        yield attr


def __getitem__(self, value):
    """
    __getitem__: MAgic Method:
        This method is invoked if you try to access an attribute which does not
        exist in the instance. We use this as an opportunity to create children.
        if you use 'key notation' indicating a valid child name then this method
        will create that child for you and return that child. Otherwise we raise
        an AttributeError.
    """
    if isinstance(value, int):
        return self._children[value]
    elif isinstance(value, str):
        try:
            return self.add_child(value)
        except InvalidChildError:
            if self.parent is not None:
                return self.parent[value]
            else:
                raise InvalidChildError
    else:
        raise AttributeError


def __getattr__(self, key):
    """
    __getattr__: Magic Method:
        This method is invoked if you try to access an attribute which does not
        exist in the instance. We use this as an opportunity to create children.
        if you use 'dot notation' indicating a valid child name then this method
        will create that child for you and return that child. Otherwise we raise
        an AttributeError.
    """
    try:
        return self.add_child(key)
    except InvalidChildError:
        if self.parent is not None:
            return self.parent[key]
        else:
            raise InvalidChildError
    return None


def __call__(self, *args, **kwargs):
    """
    __call__:
    This method is invoked when there is a call oporator after the name
    of an instance ie '()' we use this to allow for a convenient way to
    add data and attribuites to the instance. The args are joined with a
    null string to create the data and the kwargs are used to set
    attributes of the node.

    NOTE: using this method to assign data(ie. with args) will overwrite
          the existing data. If you wish to avoid this then use:
          instance.text += 'appended text'
    """
    if args:
        self.text = ''.join(args)
    if kwargs:
        self.add_attribute(**kwargs)
    return self

# Begin Monkey Patching
etree.Element.__getattr__ = __getattr__
etree.Element.__call__ = __call__
etree.Element.__getitem__ = __getitem__
etree.Element.add_child = add_child
etree.Element.add_attribute = add_attribute
etree.Element.get_path = get_path
etree.Element.parent = None
etree.Element.owner = None
etree.Element.valid_children = valid_children
etree.Element.valid_attributes = valid_attributes


class Request(object):
    def __init__(self, scheme, host, port, uri, credentials, test_case):
        """
            Class Request:
            Parameters:
                scheme:
                    type: str
                    values: http or https
                host:
                    type: str
                    values: any valid hostname
                port:
                    type: str
                    values: propper port for the web service
                uri:
                    type: str
                    values: propper uri to send requests to
                credentials:
                    type: str
                    values: username:password
                test_case:
                    type: str or etree.ElementTree
                    values: test_case generated by soapui
        """
        # Initialize class attributes
        self._pointers = {}
        self._namespace_nodes = {}
        global TIMEOUT
        self._timeout = TIMEOUT

        # handle test_case
        if isinstance(test_case, etree.ElementTree):
            # test_case is already parsed
            self._test_case = test_case
        elif isinstance(test_case, str):
            # If test_case is type str then it should be a filename
            with open(test_case, "r") as fin:
                self._test_case = cEtree.parse(fin)
        else:
            # currently we only support two types for test_case:
            # str, ElementTree
            raise InvalidTestCaseFormat

        # Populate _namespace_nodes
        for node in self._test_case.getroot().getiterator():
            if '}' in node.tag:
                ns_url, tag = node.tag.split('}')
                ns_url = ns_url.replace('{', '')
                if ns_url in self._namespace_nodes:
                    if tag not in self._namespace_nodes[ns_url]:
                        self._namespace_nodes[ns_url].append(tag)
                    else:
                        pass
                else:
                    self._namespace_nodes[ns_url] = [tag]

        # handle credentials
        self._credentials = base64.encodestring(credentials).replace('\n', '')

        # handle url
        self._url = '%s://%s:%s%s' % (scheme, host, port, uri)

        ## build template

        # get the root element
        root_tagname = self._test_case.getroot().tag
        root = etree.Element(root_tagname)
        self.root = root
        root.parent = None
        self._pointers[root_tagname.split('}')[-1]] = root

        # recursively build request with any elements having less than 3
        # children
        self.__build_template(root, self._test_case.getroot())

        # convert root element into a tree
        self.request_xml = etree.ElementTree(root)

    def set_timeout(self, timeout):
        self._timeout = int(timeout)

    def get_timeout(self):
        return self._timeout

    def valid_attributes(self, element):
        """
        valid_attributes: Public Function
            This will return the valid attributes of a given element
        """
        path = element.get_path().split('[')[0]
        for attr in self._test_case.find(path).keys():
            yield attr

    def valid_children(self, element):
        """
        valid_chidlren: Public Function:
            This will return the valid children of a given node.
        """
        path = element.get_path().split('[')[0]
        for child in self._test_case.find(path):
            yield child.tag

    def SubElement(self, parent, tag):
        """
        SubElement: Public Function:
            This is a custom wrapper around etree.SubElement.
            This should be used for all new elements with this library
            The reason is that in this library all elements have knowlege
            of their parent as well as their owner, and the request object
            has an internal dictionary of pointers which should be kept up to
            date.

            For added convenience each element has a wrapper called add_child
            which can also be accessed through key notation as well as dot
            notation. ie.

            r = Request(...)
            element = r['element'] # accesses r._pointers
            # now the next four statements are equivalent
            new_element = r.SubElement(element, 'new_element')
            new_element = element.add_child('new_element')
            new_element = element['new_element']
            new_element = element.new_element

            Also note that this will check to see if tag is a valid child of
            parent, and if not it will raise an InvalidChildError.
        """
        for ns in self._namespace_nodes:
            if tag in self._namespace_nodes[ns]:
                tag = '{%s}%s' % (ns, tag)
        if tag in self.valid_children(parent):
            new_node = etree.SubElement(parent, tag)
            new_node.parent = parent
            new_node.owner = self
            local_name = tag.split('}')[-1]
            if local_name in self._pointers:
                if isinstance(self._pointers[local_name], list):
                    self._pointers[local_name].append(new_node)
                else:
                    self._pointers[local_name] = [self._pointers[local_name],
                                                  new_node]
            else:
                self._pointers[tag.split('}')[-1]] = new_node
        else:
            raise InvalidChildError
        return new_node

    def set_attribute(self, node, **kwargs):
        """
        set_attribute: Public Function:
            This will loop through the key word arguments and set
            attributes on the node. Note, however, that this is provided
            for convenience and you should be aware of python's reserved
            words. If an attribute needs to have the name of a python
            resevred word then you should use:
                node.set('class', 'value')
                * class being a python reserved word
        """
        for key in kwargs:
            if key in self.valid_attributes(node):
                node.set(key, kwargs[key])
            else:
                raise InvalidAttributeError

    def __build_template(self, req_node, tc_node):
        """
        __build_template: private function
            This function recursively walks self._test_case and adds elements
            to self.request_xml until there are more than two children.
        """
        if len(tc_node) <= 2:
            for child in tc_node:
                new_node = etree.SubElement(req_node, child.tag)
                new_node.parent = req_node
                new_node.owner = self
                self._pointers[child.tag.split('}')[-1]] = new_node
                self.__build_template(new_node, child)

    def send(self, secure=True):
        """
        send: public function
            This function sends self.request_xml to self._url using self._creds
            for authentication and authorization. Currently only basic auth is
            supported.
        """
        import ssl
        context = ssl.create_default_context()
        if not secure:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        xml = etree.tostring(self.request_xml.getroot(), encoding="UTF-8")
        req = urllib2.Request(url=self._url, data=xml)
        creds = self._credentials.strip()
        req.add_header('Authorization', 'Basic %s' % (creds))
        response_xml = urllib2.urlopen(req, timeout=self._timeout, context=context)
        response_xml = response_xml.read()
        return response_xml

    ## Magic Methods

    def __str__(self):
        """
        __str__: Magic method:
            This is meant to produce a human readable representation
            of the object. This will alter the internal xml slightly
            in oreder to pretty print the xml.
        """
        pretty_print(self.request_xml.getroot())
        return etree.tostring(self.request_xml.getroot())

    def __repr__(self):
        """
        __repr__: Magic method:
            This is meant to produce a machine readable representation of
            the object. Note, however, that if __str__ was called previously
            that the xml will have been altered in order to pretty print the
            xml and this will be pretty printed as well.
        """
        return etree.tostring(self.request_xml.getroot())

    def __getitem__(self, key):
        """
        __getitem__: Magic Method:
            This method is provided as a convenience method to allow access
            to the internal _pointers dictionary. This dictionary is meant to
            provide an easy way to retrieve nodes from the request.
        """
        try:
            return self._pointers[key]
        except:
            raise AttributeError


def pretty_print(elem, level=0):
    """
    pretty_print: I took this from several places on the internet
        If you know where this originated, please email me at
        ilovetux@ymail.com and I will provide proper credits
        OPEN SOURCE RULES!!
    """
    i = "\n" + "  " * level
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for elem in elem:
            pretty_print(elem, level + 1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i


def pprint(xml_str):
    tree = etree.fromstring(xml_str)
    pretty_print(tree)
    return etree.tostring(tree)

if __name__ == '__main__':
    pass
