"""Small data objects used by parse.py.

Helps keep data in the parser structured. 
"""


class Signal:
    """Object to store a signal for use in the parser. Has fields for the device symbol and the port symbol.
    For example for ANDGATE1.I1, the name_symbol is the object for ANDGATE1 and the port_symbol
    is the object for I1."""

    def __init__(self, name_symbol=None, port_symbol=None, is_literal=False, literal_value = None):
        self.name_symbol = name_symbol # The name of the device or net like ANDGATE1
        self.port_symbol = port_symbol
        self.is_literal = is_literal
        self.literal_value = literal_value