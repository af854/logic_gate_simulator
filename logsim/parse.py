"""Parse the definition file and build the logic network.

Used in the Logic Simulator project to analyse the syntactic and semantic
correctness of the symbols received from the scanner and then builds the
logic network.

Classes
-------
Parser - parses the definition file and builds the logic network.
"""

from parser_objects import Signal

# This version of the parser supports syntax checks and the basic functionality
# Implemented:
# - Full syntax check
# - Make devices
# - Build connections (network)
# - Add monitors
# - Semantic error messages
# - Nets
# Not yet supported (to-do):
# - Literals
# - Modules
# - Error Recovery
# - Recursive modules (time-permitting)
#
#
# Design pattern for parsing in this file:
#   Parsing functions are based on the EBNF specification as closely as possible
#   ALL parsing functions should consume all symbols that was part of its EBNF rule,
#   leaving self.symbol on the symbol immediately after.
#   For example, parse_device should consume the ';'
#   and leave self.symbol on the symbol for the next device name, or CONNECT,
#   whichever is next.
#
# Making devices is implemented in the function parse_device()
# Making connections is implemented in the funciton parse_connect()
# Making monitors is implemented in the function parse_monitors()
#
# Net implementation:
#    Two-pass approach for building connections
#    While parsing each connection, store it in a list. 
#    Also keep track of nets and the drivers of each net.
#    Then, once all connections are parsed, process
#    them all together by resolving net references
#    to the actual output port that drives the net.
#    Two pass approach is needed since nets can be used before they
#    are driven. 


class Parser:

    """Parse the definition file and build the logic network.

    The parser deals with error handling. It analyses the syntactic and
    semantic correctness of the symbols it receives from the scanner, and
    then builds the logic network. If there are errors in the definition file,
    the parser detects this and tries to recover from it, giving helpful
    error messages.

    Parameters
    ----------
    names: instance of the names.Names() class.
    devices: instance of the devices.Devices() class.
    network: instance of the network.Network() class.
    monitors: instance of the monitors.Monitors() class.
    scanner: instance of the scanner.Scanner() class.

    Public methods
    --------------
    parse_network(self): Parses the circuit definition file.
    """

    def __init__(self, names, devices, network, monitors, scanner):
        """Initialise constants."""
        self.scanner = scanner
        self.names = names
        self.network = network
        self.devices = devices
        self.monitors = monitors

        # Store the current symbol.
        self.symbol = None
        
        self.net_ids = set() # Set that stores id of all nets. 
        self.net_driver_dict = {} # Dictionary mapping net id to its driving signal.

        # a list of tuples of Signal objects, (input signal, output signal)
        # when parsing connections, collect all the connection statements
        # into this list. Then once all connection statements are read, then we 
        # go through the list again, resolving any net references to the
        # actual aliased device output port. 
        self.pending_connections = [] 

        # Currently unused - will be used when error recovery is implemented
        self.error_count = 0



    def advance(self):
        """Advance to the next symbol."""
        self.symbol = self.scanner.get_symbol()

    def symbol_string(self):
        """Return the string name of the current symbol."""
        if self.symbol.id is None:
            return None
        return self.names.get_name_string(self.symbol.id)

    def is_keyword_name(self, name):
        """Return True if current symbol is the given keyword."""
        return (
            self.symbol.type == self.scanner.KEYWORD
            and self.symbol_string() == name
        )

    def symbol_to_string(self, symbol):
        """Return a string representation of a symbol for debugging."""
        # Debugging use only. For likely eventual removal (TODO)
        token_names = {
            self.scanner.COMMA: "COMMA",
            self.scanner.SEMICOLON: "SEMICOLON",
            self.scanner.EQUALS: "EQUALS",
            self.scanner.DOT: "DOT",
            self.scanner.L_BRACKET: "L_BRACKET",
            self.scanner.R_BRACKET: "R_BRACKET",
            self.scanner.KEYWORD: "KEYWORD",
            self.scanner.NUMBER: "NUMBER",
            self.scanner.NAME: "NAME",
            self.scanner.EOF: "EOF",
        }

        token_type = token_names.get(symbol.type, str(symbol.type))

        if symbol.id is None:
            token_id = "None"
        elif symbol.type == self.scanner.NUMBER:
            # ID of a NUMBER is the literal number (no need for lookup)
            token_id = str(symbol.id)
        else:
            token_id = self.names.get_name_string(symbol.id)

        return token_type + " " + token_id

##### ERROR HANDLING / MESSAGES #########################################################################

    # General error message
    def error(self, errormsg, symbol=None):
        """Print a descriptive error message and increment the error count.
        Takes in error message and Symbol object (default: self.symbol) as arguments. """
        if (symbol == None):
            symbol = self.symbol
        self.error_count += 1
        print("Error! " + errormsg + " | Symbol: " + self.symbol_to_string(symbol)) 
                                                    # TODO eventually remove symbol_to_string
        print("Line " + str(symbol.line_num) + ", column " + str(symbol.line_pos)+":")
        self.scanner.print_error_line(symbol.line_num, symbol.line_pos)

    # Deal with an error from Devices class
    def device_error_message(self, error_type):
        """Translate devices error code into a useful message."""
        # Of these, NO_QUALIFIER, BAD_DEVICE, and QUALIFIER_PRESENT
        # should not ever be seen since parsing device_kind
        # syntax should prevent this.
        if error_type == self.devices.NO_ERROR:
            return None
        if error_type == self.devices.INVALID_QUALIFIER:
            return "Invalid device parameter"
        if error_type == self.devices.NO_QUALIFIER:
            return "Missing device parameter"
        if error_type == self.devices.BAD_DEVICE:
            return "Unknown device kind"
        if error_type == self.devices.QUALIFIER_PRESENT:
            return "This device kind should not have a parameter"
        if error_type == self.devices.DEVICE_PRESENT:
            return "Device has already been defined"
        return "Unknown device error"
    
    def connection_error_message(self, error_type):
        """Translate network error code into a useful message."""
        if error_type == self.network.NO_ERROR:
            return None
        if error_type == self.network.INPUT_TO_INPUT:
            return "Cannot connect an input to another input"
        if error_type == self.network.OUTPUT_TO_OUTPUT:
            return "Cannot connect an output to another output"
        if error_type == self.network.INPUT_CONNECTED:
            return "Input is already connected"
        if error_type == self.network.FIRST_PORT_ABSENT or error_type == self.network.SECOND_PORT_ABSENT:
            return "Port does not exist on device"
        if error_type == self.network.FIRST_DEVICE_ABSENT or error_type == self.network.SECOND_DEVICE_ABSENT:
            return "Device does not exist"
        return "Unknown connection error"
    
    def monitor_error_message(self, error_type):
        """Translate monitors error code into a useful message."""
        if error_type == self.monitors.NO_ERROR:
            return None
        if error_type == self.monitors.NOT_OUTPUT:
            return "Signal is not a valid output to be monitored."
        if error_type == self.monitors.MONITOR_PRESENT:
            return "Signal is already being monitored"
        if error_type == self.monitors.DEVICE_ABSENT:
            return "Device does not exist"
        return "Unknown monitor error"

##### PARSING HELPER FUNCTIONS  #############################################################

    def is_parameterised_device(self):
        """Check whether the current symbol refers to a KEYWORD that represents a parametrised device:
        AND, NAND, OR, NOR, CLOCK, SWITCH."""
        if self.symbol.type != self.scanner.KEYWORD:
            return False

        return self.symbol_string() in [
            "AND",
            "NAND",
            "OR",
            "NOR",
            "CLOCK",
            "SWITCH",
        ]

    def is_fixed_device(self):
        """Check whether the current symbol refers to a KEYWORD that represents a fixed device:
        DTYPE or XOR."""
        if self.symbol.type != self.scanner.KEYWORD:
            return False

        return self.symbol_string() in [
            "DTYPE",
            "XOR",
        ]

    def device_exists(self, symbol):
        """Return True if symbol refers to an existing device and False otherwise. """
        return self.devices.get_device(symbol.id) is not None

    
##### EBNF PARSING: BASIC EBNF RULES  #######################################################

    def parse_name(self):
        """Parse a name (i.e. check if the current symbol is a scanner.NAME) 
        and return the symbol object if successful.
        Return None otherwise."""
        # We return the symbol object, not just the id, so we maintain information about the
        # symbol's location, this will be helpful for error messages.
        if self.symbol.type == self.scanner.NAME:
            name_symbol = self.symbol
            self.advance()  # consume the name
            return name_symbol

        if self.symbol.type == self.scanner.KEYWORD:
            self.error("Name cannot be a reserved keyword: " +
                       self.symbol_string())
        else:
            self.error("Expected a name and did not get one.")
        return None

    def parse_name_list(self):
        """Parse name_list based on EBNF specification.
        name_list = name, { ',', name }.
        Return list of symbol objects if successful."""

        name_list = []

        name_symbol = self.parse_name()
        if name_symbol is None:
            return None
        name_list.append(name_symbol)

        while self.symbol.type == self.scanner.COMMA:
            self.advance()

            name_symbol = self.parse_name()
            if name_symbol is None:
                return None
            name_list.append(name_symbol)

        return name_list

    def parse_signal(self):
        """Parse signal based on EBNF specification:
         signal = name, [ '.', name ].
         return Signal object if successful, None otherwise."""
        name_symbol = self.parse_name()
        if name_symbol is None:
            return None

        if self.symbol.type == self.scanner.DOT:
            self.advance()

            port_symbol = self.parse_name()
            if port_symbol is None:
                return None

            return Signal(name_symbol=name_symbol, port_symbol=port_symbol)
        return Signal(name_symbol=name_symbol, port_symbol=None)

    def parse_signal_list(self):
        """Parse signal_list based on EBNF specification: 
        signal_list = signal, { ',', signal }.
        return list of Signal objects if successful, None otherwise"""
        signal_list = []

        signal = self.parse_signal()
        if signal is None:
            return None
        signal_list.append(signal)

        while self.symbol.type == self.scanner.COMMA:
            self.advance()

            signal = self.parse_signal()
            if signal is None:
                return None
            signal_list.append(signal)

        return signal_list

    def parse_device_kind(self):
        """Parse device_kind in the EBNF:
        parametrised_device, \"(\", number, \")\",
        or fixed_device. 

        Return a tuple containing (device_kind_id, device_parameter),
        where device_kind_id is the name ID for the device string like "AND"
        and device_parameter is a plain integer, like 2 for AND(2),
         or return None if there's an error. """

        # When called should point to the symbol for the device keyword (like AND, SWITCH)
        # TODO Need to do something with this to build the network

        if self.is_parameterised_device():
            device_kind_id = self.symbol.id

            self.advance()  # consume the device type like AND
            if self.symbol.type != self.scanner.L_BRACKET:
                self.error("Expected '(' after parameterised device")
                return None
            self.advance()  # consume (

            if self.symbol.type != self.scanner.NUMBER:
                self.error("Expected number")
                return None
            device_parameter = self.symbol.id
            self.advance()  # consume the number

            if self.symbol.type != self.scanner.R_BRACKET:
                self.error("Expected ')'")
                return None

            self.advance()  # consume )
            return device_kind_id, device_parameter

        if self.is_fixed_device():
            device_kind_id = self.symbol.id
            self.advance()  # consume the device type like XOR
            return device_kind_id, None

        self.error("Invalid device kind.")
        return None
    
##### PARSING NETS AND NET HELPER FUNCTIONS #############################################################

    def is_net(self, signal):
        return signal.name_symbol.id in self.net_ids and signal.port_symbol is None
    
    def net_used_with_port(self, signal):
        """Return True if signal uses a declared net name with a port."""
        return (
            signal.name_symbol.id in self.net_ids
            and signal.port_symbol is not None
        )

    def parse_net_declaration(self):
        """Parse a net declaration statement:
          name_list, ';'."""
        
        # 1. EBNF based syntax and collect the names of the nets 
        net_symbols = self.parse_name_list()

        if net_symbols is None:
            return False

        if self.symbol.type != self.scanner.SEMICOLON:
            self.error("Expected semicolon after net declaration")
            return False

        self.advance()

        # 2. Semantic checks and create the actual nets.

        for net_symbol in net_symbols:
            if self.device_exists(net_symbol):  # if a device already exists with the same name/id
                # n.b. we dont need checks the other way (i.e. device name conflicts with net name)
                # since device section is always before the nets section. 
                self.error("Net name conflicts with an existing device name", net_symbol)
                return False
            
            net_id = net_symbol.id
            # keep track of existing nets
            if net_id in self.net_ids:
                self.error("Net has already been declared", net_symbol)
                return False
            self.net_ids.add(net_id)

        return True
    
    def parse_nets(self):
        """Parse the NETS section.
        Return True if successful and False otherwise. """
        while True:
            if self.is_keyword_name("CONNECT"): # end of NETS section. 
                return True

            if self.symbol.type == self.scanner.EOF:
                self.error("Unexpected end of file in NETS section - should be followed by CONNECT section.")
                return False

            if not self.parse_net_declaration():
                return False
            
    def flatten_net_driver_dict(self):
        """Flatten net_driver_dict, so that the driver of every
        net becomes the actual device output signal (instead of 
        another net.) Return True if successful, and False otherwise."""

        # Basically if we have
        # net1 = net2; net2 = AND1.I1,
        # this flattens net_driver_dict[net1] to be AND1.I1, not net2.
        for net_id in list(self.net_driver_dict.keys()):
            seen_net_ids = {net_id}
            driver = self.net_driver_dict[net_id]
            while self.is_net(driver):
                driver_net_id = driver.name_symbol.id
                if driver_net_id in seen_net_ids:
                    self.error("Circular definition of nets detected", driver.name_symbol)
                    return False

                if driver_net_id not in self.net_driver_dict:
                    self.error("Net has no driver", driver.name_symbol)
                    return False

                seen_net_ids.add(driver_net_id)
                driver = self.net_driver_dict[driver_net_id]
            self.net_driver_dict[net_id] = driver

        return True

    
    
##### EBNF PARSING: DEVICES, CONNECT, AND MONITOR ##################################################

    def parse_device(self):
        """Parse device based on EBNF specification:
         device = name_list, '=', device_kind, ';'.
         Return True if successful, False otherwise"""

        # 1. Parse the device ebnf rule (syntax)

        device_name_list = self.parse_name_list()
        if device_name_list is None:
            return False

        if self.symbol.type != self.scanner.EQUALS:
            self.error("No equals found after device name.")
            return False

        self.advance()

        device_kind_symbol = self.symbol

        device_kind_result = self.parse_device_kind()
        if (device_kind_result is None):
            return False
        device_kind_id, device_parameter = device_kind_result

        if self.symbol.type != self.scanner.SEMICOLON:
            self.error("No Semicolon found after device definition")
            return False

        self.advance()  # Consume semicolon

        # 2. Actually make the device (and semantic checks)

        for device_name in device_name_list:  # device_name is a symbol
            error_type = self.devices.make_device(
                device_name.id,
                device_kind_id,
                device_parameter,
            )

            # string for the error message, or None if no error
            error_message = self.device_error_message(error_type)

            if error_message is not None:
                if error_type == self.devices.INVALID_QUALIFIER:
                    # Only in the case of INVALID_QUALIFIER, we should point to
                    # the device kind symbol; otherwise we should point to the device name.
                    # All other errors involving the device kind should have been
                    # caught by parse_device_kind.
                    self.error(error_message, device_kind_symbol)
                else:
                    # e.g. DEVICE_PRESENT: duplicate device
                    self.error(error_message, device_name)
                return False

        return True

    def parse_devices(self):
        """Parse a list of devices, { device }. 
        return True if successful.
        """
        while True:
            if self.is_keyword_name("CONNECT") or self.is_keyword_name("NETS"):
                return True

            if self.symbol.type == self.scanner.EOF:
                self.error(
                    "Unexpected end of file in DEVICES section - ensure the file has CONNECT and MONITOR sections.")
                return False

            if not self.parse_device():
                return False

    def parse_connect(self):
        """Parse connect based on EBNF specification.
        connect = signal_list, '=', signal, ';'.
        Add all the connections to be made to pending_connections,
        and build net_driver_dict. 
        Return True if successful, false otherwise."""

        # 1. Parse the device EBNF rule (syntax)

        input_signal_list = self.parse_signal_list() 
        if input_signal_list is None:
            return False

        if self.symbol.type != self.scanner.EQUALS:
            self.error("Expected '=' in connection")
            return False

        self.advance() # consume equals

        output_signal = self.parse_signal()
        if output_signal is None:
            return False

        if self.symbol.type != self.scanner.SEMICOLON:
            self.error("Expected semicolon after connection")
            return False

        self.advance()

        # 2. Store the connections to be made, and some net semantic checks
        #     (other semantic checks performed during resolve_and_create_connections)

        if self.net_used_with_port(output_signal):
            self.error("Net cannot have a port", output_signal.port_symbol)
            return False


        for input_signal in input_signal_list:
            # If the LHS is a net, we store its RHS in net_driver_dict
            # (RHS can also be a net, this will be flattened with a call
            # to flatten_net_driver_dict during resolve_and_create_connections)
            if self.net_used_with_port(input_signal):
                self.error("Net cannot have a port", output_signal.port_symbol)
                return False
            if self.is_net(input_signal):
                net_id = input_signal.name_symbol.id
                if(net_id not in self.net_driver_dict):
                    self.net_driver_dict[net_id] = output_signal
                else:
                    self.error("Net has multiple drivers", input_signal.name_symbol)
                    return False
                
            # Otherwise if LHS is a regular signal we just add it to the 
            # pending connections list. 
            else:
                self.pending_connections.append((input_signal, output_signal))

        return True
    
    def resolve_and_create_connections (self):
        """Resolve all net references in pending_connections, 
        then create all the connections in the network. Return True if successful, False otherwise"""

        if not self.flatten_net_driver_dict():
            return False
        
        for connection in self.pending_connections:
            input_signal, output_signal = connection

            input_device_id = input_signal.name_symbol.id
            input_port_id = None if input_signal.port_symbol is None else input_signal.port_symbol.id

            if self.is_net(output_signal):
                net_id = output_signal.name_symbol.id

                if net_id not in self.net_driver_dict:
                    self.error("Net has no driver", output_signal.name_symbol)
                    return False

                output_signal = self.net_driver_dict[net_id]
            
            output_device_id = output_signal.name_symbol.id
            output_port_id = None if output_signal.port_symbol is None else output_signal.port_symbol.id

            # input_signal is the destination; output_signal is now resolved to the actual driver            
            connection_error_type = self.network.make_connection(
                input_device_id, input_port_id, output_device_id, output_port_id
            )

            error_message = self.connection_error_message(connection_error_type)
            best_error_symbol = self.symbol # the best symbol we should point to
                                            # for the most descriptive error message.
            if error_message is not None:
                # network.py was changed so DEVICE_ABSENT is split into 
                # FIRST_ or SECOND_DEVICE_ABSENT, and same for PORT_ABSENT.
                # This allows us to always point at the most relevant symbol in error msg.
                if connection_error_type == self.network.FIRST_DEVICE_ABSENT:
                    best_error_symbol = input_signal.name_symbol
                elif connection_error_type == self.network.FIRST_PORT_ABSENT:   
                    best_error_symbol = input_signal.port_symbol
                elif connection_error_type == self.network.SECOND_DEVICE_ABSENT:
                    best_error_symbol = output_signal.name_symbol
                elif connection_error_type == self.network.SECOND_PORT_ABSENT:   
                    best_error_symbol = output_signal.port_symbol
                elif connection_error_type == self.network.INPUT_CONNECTED or connection_error_type == self.network.OUTPUT_TO_OUTPUT:
                    if input_signal.port_symbol is None:
                        best_error_symbol = input_signal.name_symbol 
                    else:
                        best_error_symbol = input_signal.port_symbol
                elif connection_error_type == self.network.INPUT_TO_INPUT:
                    if output_signal.port_symbol is None:
                        best_error_symbol = output_signal.name_symbol 
                    else:
                        best_error_symbol = output_signal.port_symbol
                self.error(error_message, best_error_symbol)
                return False
        return True


    def parse_connections(self):
        """Parse connections based on EBNF specification:
         connections = { connect }.
         return True if successful."""
        while True:
            if self.is_keyword_name("MONITOR"):
                return self.resolve_and_create_connections()

            if self.symbol.type == self.scanner.EOF:
                self.error("Unexpected end of file in CONNECT section")
                return False

            if not self.parse_connect():
                return False
                

    def parse_monitors(self):
        """Parse EBNF for monitors section: 
            { signal_list, ";" }
            Return True if successful, False otherwise.
        """

        # 1. parse the syntax according to EBNF

        all_monitors_list = []
        while True:

            if self.symbol.type == self.scanner.EOF:
                break
            
            monitor_signals = self.parse_signal_list()
            if monitor_signals is None:
                return False
            
            all_monitors_list.extend(monitor_signals)

            if self.symbol.type != self.scanner.SEMICOLON:
                self.error("Expected semicolon after monitor definition")
                return False

            self.advance()  # consume the semicolon.

        # 2. create the monitors and detect semantic errors

        for monitor_signal in all_monitors_list:

            # The display name for the monitor should be the actual name of the net
            # specified, if the user wants to monitor a net. Thus we store
            # the display name before we resolve the net
            display_name = self.names.get_name_string(monitor_signal.name_symbol.id)
            if monitor_signal.port_symbol is not None:
                display_name.append(self.names.get_name_string(monitor_signal.port_symbol.id))

            # Resolve the net reference
            if self.is_net(monitor_signal):
                net_id = monitor_signal.name_symbol.id

                if net_id not in self.net_driver_dict:
                    self.error("Net has no driver", monitor_signal.name_symbol)
                    return False

                monitor_signal = self.net_driver_dict[net_id]

            device_id = monitor_signal.name_symbol.id
            port_id = None if monitor_signal.port_symbol is None else monitor_signal.port_symbol.id
            
            error_type = self.monitors.make_monitor(device_id, port_id)

            error_message = self.monitor_error_message(error_type)
            error_symbol = self.symbol
            if error_message is not None:
                if(monitor_signal.port_symbol is None):
                    error_symbol = monitor_signal.name_symbol
                else:
                    error_symbol = monitor_signal.port_symbol
                    # TODO right now, we always point to the port if it exists,
                    # and point to the device otherwise. This is usually OK
                    # but for DEVICE_ABSENT we might want to check if the
                    # device is absent or the device exists but port absent,
                    # and change this accordingly. 

                    # TODO Additionally, as long as the device exists
                    # the error message is "not a valid output" - 
                    # could make this more helpful by making it clear
                    # e.g. monitor FF1, FF1.I1, FF1.asdf all currently give
                    # same error messages. This is not a huge deal but
                    # to be more helpful we could try to
                    # differentiate between:
                    #      port exists but is not an output,
                    #      port does not exist on device
                    #      device has multiple output ports - need to specify

                self.error(error_message, error_symbol)
                return False
            self.monitors.set_monitor_display_name(device_id, port_id, display_name)
        return True 

##### PARSING: FULL NETWORK (TOP LEVEL FUNCTION) #################################################

    def parse_network(self):
        """Parse the full circuit definition file."""

        # self.symbol starts on None, advance it once to get the first symbol
        self.advance()

        if self.is_keyword_name("DEVICES"):
            self.advance()

            if not self.parse_devices():
                return False
        else:
            self.error(
                "Error: DEVICES section not found at the start of the file")
            return False
        
        if self.is_keyword_name("NETS"):
            self.advance()

            if not self.parse_nets():
                return False

        if self.is_keyword_name("CONNECT"):
            self.advance()

            if not self.parse_connections():
                return False
        else:
            self.error("Error: CONNECT section not found after DEVICES section")
            return False

        if self.is_keyword_name("MONITOR"):
            self.advance()

            if not self.parse_monitors():
                return False
        else:
            self.error("Error: MONITOR section not found after CONNECT section")
            return False

        if self.symbol.type != self.scanner.EOF:
            self.error("Expected end of file - MONITOR section should be the final section")
            return False

        if self.error_count == 0:
            print("Process finished with no error")
            return True

        return False
