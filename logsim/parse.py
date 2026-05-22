"""Parse the definition file and build the logic network.

Used in the Logic Simulator project to analyse the syntactic and semantic
correctness of the symbols received from the scanner and then builds the
logic network.

Classes
-------
Parser - parses the definition file and builds the logic network.
"""


# In this entire file 

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

        # Store the current symbol.
        self.symbol = None # 
        self.error_count = 0

    def advance(self):
        """Advance to the next symbol."""
        self.symbol = self.scanner.get_symbol()

    def symbol_name(self):
        """Return the string name of the current symbol."""
        if self.symbol.id is None:
            return None
        return self.names.get_name_string(self.symbol.id)

    def is_keyword_name(self, name):
        """Return True if current symbol is the given keyword."""
        return (
            self.symbol.type == self.scanner.KEYWORD
            and self.symbol_name() == name
        )

    def symbol_to_string(self, symbol):
        """Return a string representation of a symbol for debugging."""
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
        else:
            token_id = self.names.get_name_string(symbol.id)

        return token_type + " " + token_id
    
        
    def error(self, errormsg, symbol=None):
        """Print a descriptive error message and increment the error count.
        Takes in error message and Symbol object (default: self.symbol) as arguments. """
        if(symbol==None):
            symbol = self.symbol
        self.error_count += 1
        print("Error! " + errormsg + " | Symbol: " + self.symbol_to_string(symbol))
        print("Line " + str(symbol.line_num) + ", column " + str(symbol.line_pos)+":")
        self.scanner.print_error_line(symbol.line_num, symbol.line_pos)


    def parse_name(self):
        """Parse a name, and return True if successful."""
        if self.symbol.type == self.scanner.NAME:
            self.advance()
            return True

        self.error("Expected a name and didn't get one")
        return False

    def parse_name_list(self):
        """Parse name_list based on EBNF specification.
        name_list = name, { ',', name }.
        Return True if successful."""
        if not self.parse_name():
            return False

        while self.symbol.type == self.scanner.COMMA:
            self.advance()

            if not self.parse_name():
                return False

        return True

    def is_parameterised_device(self):
        """Check whether the current symbol refers to a KEYWORD that represents a parametrised device:
        AND, NAND, OR, NOR, CLOCK, SWITCH."""
        if self.symbol.type != self.scanner.KEYWORD:
            return False

        return self.symbol_name() in [
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

        return self.symbol_name() in [
            "DTYPE",
            "XOR",
        ]

    def parse_device_kind(self):
        """Parse device_kind in the EBNF:
        parametrised_device, \"(\", number, \")\",
        or fixed_device. Return True if successful."""

        # When called should point to the symbol for the device keyword (like AND, SWITCH)
        # TODO Need to do something with this to build the network

        if self.is_parameterised_device():
            self.advance()

            if self.symbol.type != self.scanner.L_BRACKET:
                self.error("Expected '(' after parameterised device")
                return False
            self.advance()

            if self.symbol.type != self.scanner.NUMBER:
                self.error("Expected number")
                return False

            self.advance()

            if self.symbol.type != self.scanner.R_BRACKET:
                self.error("Expected ')'")
                return False

            self.advance()
            return True

        if self.is_fixed_device():
            self.advance()
            return True

        self.error("Expected device kind")
        return False

    def parse_device(self):
        """Parse device based on EBNF specification:
         device = name_list, '=', device_kind, ';'.
         Return True if successful."""
        if not self.parse_name_list():
            return False

        if self.symbol.type != self.scanner.EQUALS:
            self.error("No equals found after device name")
            return False

        self.advance()

        if not self.parse_device_kind():
            return False

        if self.symbol.type != self.scanner.SEMICOLON:
            self.error("No Semicolon found after device definition")
            return False

        self.advance()
        return True

    def parse_devices(self):
        """Parse a list of devices, { device }. 
        return True if successful.
        """
        while True:
            if self.is_keyword_name("CONNECT"):
                return True

            if self.symbol.type == self.scanner.EOF:
                self.error("Unexpected end of file in DEVICES section")
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
        connect = signal, { ',', signal }, '=', signal, ';'.
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

    def parse_monitor(self):
        """Parse monitor = signal, { ',', signal }, ';'."""
        if not self.parse_signal_list():
            return False

        if self.symbol.type != self.scanner.SEMICOLON:
            self.error("Expected semicolon after monitor")
            return False

        self.advance()
        return True

    def parse_monitors(self):
        """Parse { monitor }."""
        while True:
            if self.symbol.type == self.scanner.EOF:
                return True

            if not self.parse_monitor():
                return False

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