#!/usr/bin/env python

class Plugin(object):
    def __init__(self):
        pass

    def html(self):
        raise NotImplementedError

    def css(self):
        raise NotImplementedError

    def js(self):
        raise NotImplementedError

    def route(self):
        raise NotImplementedError

    def config(self):
        raise NotImplementedError


