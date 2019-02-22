
def insert_newlines(string, every=64):
    return '\n'.join(string[i:i+every] for i in xrange(0, len(string), every))
