"""Small data objects used by parse.py.

Helps keep data in the parser structured. 
"""


class Signal:
    """Object to store a signal for use in the parser. Has fields for the device symbol and the port symbol.
    For example for ANDGATE1.I1, the main_symbol is the object for ANDGATE1 and the port_symbol
    is the object for I1."""

    def __init__(self, main_symbol=None, port_symbol=None, is_literal=False, literal_value = None, main_id = None, port_id = None):
        self.main_symbol = main_symbol # The name of the device or net like ANDGATE1
        self.port_symbol = port_symbol
        self.is_literal = is_literal
        self.literal_value = literal_value

        # Here, if the Signal is a real signal, pointing to a real device directly in the network,
        # then main_id and port_id can just be found from the main_symbol and port_symbol.
        #
        # However, adding these fields also allows devices to have IDs that are separate from
        # the symbol id. This is useful for devices instantiated inside modules.
        # For such a device, the main_symbol and port_symbol will point to the symbols written
        # in the module instantiation, but the main_id will be, for example,
        # MODULE_INSTANCE_NAME->DEVICE_NAME, the internal device name used to keep track of
        # different module instances' devices. (since MODULE_INSTANCE_NAME->DEVICE_NAME)
        # is not actually written in the code anywhere. 

        if main_id is None and main_symbol is not None:
            self.main_id = main_symbol.id
        else:
            self.main_id = main_id
        if port_id is None and port_symbol is not None:
            self.port_id = port_symbol.id
        else:
            self.port_id = port_id

class ModuleDevice:
    """Object that details about one device inside a module definition."""

    def __init__(self, symbol, kind_type, kind_name, parameter_value):
        self.symbol = symbol
        self.kind_type = kind_type      # "primitive" or "module"
        self.kind_name = kind_name      # e.g. "AND" or another module name
        self.parameter_value = parameter_value

class ModuleDefinition:
    """Object that systematically stores all details of a module definition."""

    def __init__(self, name_symbol, input_symbols, output_symbols):
        self.name_symbol = name_symbol

        self.input_symbols = input_symbols
        self.output_symbols = output_symbols

        self.devices = [] # list of Devices

        self.net_driver_dict = {} # dict from net_id to its driving signal

        # sets to keep track of ids of names - for easy duplicate detection
        self.input_ids = set()
        self.output_ids = set()
        self.device_ids = set()
        self.net_ids = set()

        for input_symbol in input_symbols:
            self.input_ids.add(input_symbol.id)
        for output_symbol in output_symbols:
            self.output_ids.add(output_symbol.id)

        self.connections = [] # list of tuples of connection symbols (destination, driver) 