"""Parse the definition file and build the logic network.

Used in the Logic Simulator project to analyse the syntactic and semantic
correctness of the symbols received from the scanner and then builds the
logic network.

Classes
-------
Parser - parses the definition file and builds the logic network.
"""

# This version of the parser supports syntax checks and the basic functionality
# Implemented:
# - Syntax 
# - Make the devices
# Not yet supported (to-do):
# - Build the network connections
# - Monitors 
# - Semantic errors
# - Literals
# - Nets
# - Modules
# - Recursive modules (time-permitting)

# Design pattern for parsing in this file:
# Parsing functions are based on the EBNF specification as closely as possible
# ALL parsing functions should consume all symbols that was part of its EBNF rule,
# leaving self.symbol on the symbol immediately after. 
# For example, parse_device should consume the ';'
# and leave self.symbol on the symbol for the next device name, or CONNECT,
# whichever is next.

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
        self.symbol = None # 
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
        # Debugging use only. For likely eventual removal. 
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
            token_id = str(symbol.id) # ID of a NUMBER is the literal number (no need for lookup)
        else:
            token_id = self.names.get_name_string(symbol.id)

        return token_type + " " + token_id
    
    # ERROR HANDLING / MESSAGES #################################################################
    
    # General error message 
    def error(self, errormsg, symbol=None):
        """Print a descriptive error message and increment the error count.
        Takes in error message and Symbol object (default: self.symbol) as arguments. """
        if(symbol==None):
            symbol = self.symbol
        self.error_count += 1
        print("Error! " + errormsg + " | Symbol: " + self.symbol_to_string(symbol))
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
    

    # EBNF RULE-BASED PARSING #################################################################

    def parse_name(self):
        """Parse a name (i.e. check if the current symbol is a scanner.NAME) 
        and return the symbol object if successful.
        Return None otherwise."""
        # We return the symbol object, not just the id, so we maintain information about the
        # symbol's location, this will be helpful for error messages.
        if self.symbol.type == self.scanner.NAME:
            name_symbol = self.symbol
            self.advance() # consume the name
            return name_symbol
        
        if self.symbol.type == self.scanner.KEYWORD:
            self.error("Name cannot be a reserved keyword: "+self.symbol_string())
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

            self.advance() # consume the device type like AND
            if self.symbol.type != self.scanner.L_BRACKET:
                self.error("Expected '(' after parameterised device")
                return None
            self.advance() # consume (

            if self.symbol.type != self.scanner.NUMBER:
                self.error("Expected number")
                return None
            device_parameter = self.symbol.id
            self.advance() # consume the number

            if self.symbol.type != self.scanner.R_BRACKET:
                self.error("Expected ')'")
                return None
            
            self.advance() # consume )
            return device_kind_id, device_parameter

        if self.is_fixed_device():
            device_kind_id = self.symbol.id
            self.advance() # consume the device type like XOR
            return device_kind_id, None

        self.error("Invalid device kind.")
        return None

    def parse_device(self):
        """Parse device based on EBNF specification:
         device = name_list, '=', device_kind, ';'.
         Return True if successful, False otherwise"""
        
        # 1. Parse the device ebnf rule

        device_name_list = self.parse_name_list()
        if device_name_list is None:
            return False

        if self.symbol.type != self.scanner.EQUALS:
            self.error("No equals found after device name.")
            return False

        self.advance()

        device_kind_symbol = self.symbol 

        device_kind_result = self.parse_device_kind()
        if(device_kind_result is None):
            return False
        device_kind_id, device_parameter = device_kind_result

        if self.symbol.type != self.scanner.SEMICOLON:
            self.error("No Semicolon found after device definition")
            return False
        
        self.advance() # Consume semicolon

        # 2. Actually make the device

        for device_name in device_name_list: # device_name is a symbol
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
            if self.is_keyword_name("CONNECT"):
                return True

            if self.symbol.type == self.scanner.EOF:
                self.error("Unexpected end of file in DEVICES section - ensure the file has CONNECT and MONITOR sections.")
                return False

            if not self.parse_device():
                return False

    def parse_signal(self):
        """Parse signal based on EBNF specification:
         signal = name, [ '.', name ].
         return True if successful."""
        if not self.parse_name():
            return False

        if self.symbol.type == self.scanner.DOT:
            self.advance()

            if not self.parse_name():
                return False

        return True

    def parse_signal_list(self):
        """Parse signal_list based on EBNF specification: 
        signal_list = signal, { ',', signal }.
        return True if successful."""
        if not self.parse_signal():
            return False

        while self.symbol.type == self.scanner.COMMA:
            self.advance()

            if not self.parse_signal():
                return False

        return True

    def parse_connect(self):
        """Parse connect based on EBNF specification.
        connect = signal_list, '=', signal, ';'.
        return True if successful."""
        if not self.parse_signal_list():
            return False

        if self.symbol.type != self.scanner.EQUALS:
            self.error("Expected '=' in connection")
            return False

        self.advance()

        if not self.parse_signal():
            return False

        if self.symbol.type != self.scanner.SEMICOLON:
            self.error("Expected semicolon after connection")
            return False

        self.advance()
        return True

    def parse_connections(self):
        """Parse connections based on EBNF specification:
         connections = { connect }.
         return True if successful."""
        while True:
            if self.is_keyword_name("MONITOR"):
                return True

            if self.symbol.type == self.scanner.EOF:
                self.error("Unexpected end of file in CONNECT section")
                return False

            if not self.parse_connect():
                return False

    def parse_monitors(self):
        """Parse { signal_list, ";" }."""
        while True:
            if self.symbol.type == self.scanner.EOF:
                return True

            if not self.parse_signal_list():
                return False
                        
            if self.symbol.type != self.scanner.SEMICOLON:
                self.error("Expected semicolon after monitor definition")
                return False
            
            self.advance() # consume the semicolon. 

    def parse_network(self):
        """Parse the circuit definition file."""

        # self.symbol starts on None, advance it once to get the first symbol
        self.advance()

        if self.is_keyword_name("DEVICES"):
            self.advance()

            if not self.parse_devices():
                return False
        else:
            self.error("Error: DEVICES section not found at the start of the file")
            return False

        if self.is_keyword_name("CONNECT"):
            self.advance()

            if not self.parse_connections():
                return False
        else:
            self.error("Error: CONNECT section not found")
            return False

        if self.is_keyword_name("MONITOR"):
            self.advance()

            if not self.parse_monitors():
                return False
        else:
            self.error("Error: MONITOR section not found")
            return False

        if self.symbol.type != self.scanner.EOF:
            self.error("Expected end of file after MONITOR section")
            return False

        if self.error_count == 0:
            print("Process finished with no error")
            return True

        return False