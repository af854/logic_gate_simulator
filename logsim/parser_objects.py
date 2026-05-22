"""Small data objects used by parse.py.

Helps keep data in the parser structured. 
"""


class Signal:
    """Object to store a signal for use in the parser. Has fields for the device symbol and the port symbol.
    For example for ANDGATE1.I1, the device symbol is the object for ANDGATE1 and the port symbol
    is the object for I1."""

    def __init__(self, device_symbol=None, port_symbol=None):
        self.device_symbol = device_symbol
        self.port_symbol = port_symbol