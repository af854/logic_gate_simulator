"""Define small data objects used by parse.py.

These classes help keep data in the parser structured.
"""


class Signal:
    """Store a parsed signal, module signal, net, or literal.

    A Signal normally represents something like ANDGATE1.I1, where
    main_symbol stores the symbol for ANDGATE1 and port_symbol stores the
    symbol for I1. It can also represent a net, a module port, or a literal.
    """

    def __init__(
        self,
        main_symbol=None,
        port_symbol=None,
        is_literal=False,
        literal_value=None,
        main_id=None,
        port_id=None,
    ):
        """Initialise a Signal object.

        Optional keyword arguments:
        main_symbol -- Symbol object for the main signal name, such as a
            device, net, or module port name.
        port_symbol -- Symbol object for the port name, or None if the signal
            has no explicit port.
        is_literal -- True if this Signal represents literal 0 or 1.
        literal_value -- integer value of the literal when is_literal is True.
        main_id -- internal ID to use instead of main_symbol.id.
        port_id -- internal port ID to use instead of port_symbol.id.

        """
        self.main_symbol = main_symbol  # The name of the device or net like ANDGATE1
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
    """Store one device declared inside a module definition.

    The stored device may be either a primitive device, such as AND or CLOCK,
    or an instantiation of another user-defined module.
    """

    def __init__(self, symbol, kind_type, kind_name, parameter_value, kind_symbol=None):
        """Initialise a ModuleDevice object.

        Arguments:
        symbol -- Symbol object for the device instance name.
        kind_type -- string identifying the kind as "primitive" or "module".
        kind_name -- name ID of the primitive device or module being instantiated.
        parameter_value -- integer parameter value for parameterised primitive
            devices, or None if no parameter is used.
        kind_symbol -- Symbol object for device kind or module type
        """
        self.symbol = symbol
        self.kind_type = kind_type  # "primitive" or "module"
        self.kind_name = kind_name  # e.g. ID for "AND" or another module name
        self.parameter_value = parameter_value
        self.kind_symbol = kind_symbol


class ModuleDefinition:
    """Store all parser information for one module definition.

    A ModuleDefinition records the module interface, devices, nets,
    connections, and ID sets needed for duplicate detection and later module
    expansion.
    """

    def __init__(self, name_symbol, input_symbols, output_symbols):
        """Initialise a ModuleDefinition object.

        Arguments:
        name_symbol -- Symbol object for the module name.
        input_symbols -- list of Symbol objects for the module input ports.
        output_symbols -- list of Symbol objects for the module output ports.

        Also initialise empty containers for
        devices, nets, drivers, and connections. Populate input_ids and
        output_ids from the supplied input and output symbols.
        """
        self.name_symbol = name_symbol

        self.input_symbols = input_symbols
        self.output_symbols = output_symbols

        self.devices = []  # list of Devices

        self.net_driver_dict = {}  # dict from net_id to its driving signal

        # sets to keep track of ids of names - for easy duplicate detection
        self.input_ids = set()
        self.output_ids = set()
        self.device_ids = set()
        self.net_ids = set()

        for input_symbol in input_symbols:
            self.input_ids.add(input_symbol.id)
        for output_symbol in output_symbols:
            self.output_ids.add(output_symbol.id)

        self.connections = []  # list of tuples of connection symbols (destination, driver)
