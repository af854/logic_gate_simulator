"""Parse the definition file and build the logic network.

Used in the Logic Simulator project to analyse the syntactic and semantic
correctness of the symbols received from the scanner and then builds the
logic network.

Classes
-------
Parser - parses the definition file and builds the logic network.
"""

from parser_objects import Signal, ModuleDefinition, ModuleDevice

MAX_ERROR_MSGS = 7

# Implemented:
# - Full syntax check
# - Make devices
# - Build connections (network)
# - Add monitors
# - Semantic error messages
# - Nets
# - Literals
# - Modules
# - Hierarchical modules 
# - Error Recovery
# - Typo hints
#
#
# Design pattern for parsing in this file:
#    Parsing functions are based on the EBNF specification as closely as possible
#    ALL parsing functions should consume all symbols that was part of its EBNF rule,
#    leaving self.symbol on the symbol immediately after.
#    For example, parse_device should consume the ';'
#    and leave self.symbol on the symbol for the next device kind, or CONNECT/NETS,
#    whichever is next.
#
#    - In general, syntax parsing functions that return an object return
#    the object if successful, and None if unsuccessful (after which
#    it also leaves the parser in a synchronized state).
# 
#    - Parsing functions that only parse without returning an object
#    return True if the parser is still in a known state (regardless
#    of whether syntax or semantic checks were successful),
#    and return False if the parser got lost (for example, after
#    seeing unexpected structure like section keyword in an unexpected
#    place.), typically checked in a section-level parsing function.
#    
#    - Semantic check or network building methods typically 
#    just return, either when they are done or when the processing is 
#    being skipped due to previous errors. . Whether or not there have 
#    been semantic errors is tracked through self.error_count.
#
# Summary of module and nets implementation:
#    Devices inside a module instance get turned to devices
#    with the name INSTANCENAME->DEVICENAME
#    Module input and output ports get turned into nets with 
#    the name INSTANCENAME->PORTNAME
#    Nets inside a module get turned into nets with
#    the name INSTANCENAME->NETNAME
#    (Hierarchical modules automatically get names like
#    INSTANCENAME->SUB_INSTANCENAME->...->NAME)
#    Then we gather all the connections, 
#    resolve all net references to their drivers,
#    and build the connections. 
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
#
# Literal implementation:
#    We create a SWITCH(0) or SWITCH(1) device, used internally only
#    to provide the literal 0 or 1 signals.
#
# Module implementation:
#    When parsing the module definition, we first store it as a 
#    ModuleDefinition object that contains all the information
#    needed to build instances of this module. 
#    This uses a separate set of parsing functions parse_module_xxxx
#    
#    We treat the input and output ports of the module as internal nets, 
#    and when instantiating the module, we create new devices
#    and signals using an internal name for each instance of the 
#    module e.g. INSTANCENAME->SIGNALNAME (using name_id and port_id)
#    of the Signal class. 
#
#    Then the rest continues as usual - we just add the module's internal
#    connections to pending_connections, and make sure to use the internal net/device
#    names whenever we see a module instance input/output port
#    when making connnections and monitors in the main circuit.
#
# Hierarchical modules:
#    The code is already written in a way that makes hierarchical modules 
#    relatively straightforward.
#    A new field is added to instantiate_module and all related methods
#    to allow storage of instance_id which can be different from the instance_symbol
#    (see instantiate_module comments)
#    
#    We recursively call instantiate_module to instantiate the hierarchy.
#    Hierarchical modules and names inside have IDs with extra ->: for example
#    FULLADDER1->HALFADDER->XOR1
#    
#    instantiate_module is also updated to deal with seeing module signals
#    inside the instantiation - these must be translated to the internal
#    net/device names. 
#
# Error Recovery:
#    We try to keep building as much of the circuit as possible
#    by skipping to a synchronizing character (such as a ; or a section
#    keyword) and resuming from there (if it makes sense to do so).
#
#    Certain structural errors (e.g. missing or out of order section keywords)
#    may cause an "fatal" error and stops parsing. 
# 
#    Once the first error is found, attempts to build the network are abandoned
#    as per the client specification. Only syntax checks will be performed
#    for the remainder of the file. 
# 
# Typo hints:
#    Checks possible typos in two situations:
#      - Possible missing/typoed section keyword 
#      - Possible typo in signal (device/port/module instance) name
#   
#    TODO combinational loop checks
#    TODO PEP8 formatting compliance and finish docstrings

class Parser:

    """Parse the definition file and build the logic network.

    The parser deals with error handling. It analyses the syntactic and
    semantic correctness of the symbols it receives from the scanner, and
    then builds the logic network. If there are errors in the definition file,
    the parser detects this and tries to recover from it, giving helpful.
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
        # This extra pass is because we allow nets to be used as a source
        # before they are driven in the code.
        self.pending_connections = [] 

        # A dictionary that stores module definitions. 
        # Key is string of the module name, like "HALFADDER"
        # Value is the module object. 
        self.module_definitions = {}

        # Set for module instance name IDs for detecting duplicates
        self.module_instance_ids = set()

        # Dict that maps (instance_id, port_id) to internal Signal, e.g.
        # (H1, A) -> Signal(main_id=H1->A)
        self.module_instance_ports = {}

        # Maps (instance_id, port_id) to "input" or "output"
        self.module_instance_port_directions = {}

        # Keep track of device declaration symbols to point to them easily
        # for device input not driven error msg
        self.device_declaration_symbols = {}
        # Maps internal primitive device id to the module type it came from.
        # e.g. id("H1->X1") -> "HALFADDER". Used to display appropriate error msg
        # for device not driven within module
        # This allows using existing devices.py logic to check for undriven inputs
        self.device_module_names = {}

        # Dict from section keyword like "INPUTS" to 
        # Symbol of a potential typo
        self.possible_typo_symbols = {}

        self.section_keyword_strings = ["MODULE", "INPUTS", "OUTPUTS", "DEVICES", "NETS", "CONNECT", "MONITOR", "ENDMODULE"]

        # Currently unused - will be used when error recovery is implemented
        self.error_count = 0

    def advance(self):
        """Advance to the next symbol."""
        self.symbol = self.scanner.get_symbol()
        while self.symbol.type == self.scanner.UNKNOWN:
            self.error("Invalid symbol or character!")
            self.symbol = self.scanner.get_symbol()


        # Keep track of possible typoed section keywords for more
        # informative error messages and preventing
        # cascading error messages due to missing/typoed section keyword
        if self.symbol.type == self.scanner.NAME:
            for section_keyword_string in self.section_keyword_strings:
                if self.possible_typo(self.symbol_string(), section_keyword_string):
                    self.possible_typo_symbols[section_keyword_string] = self.symbol
        

    def synchronize(self, stopping_types=None):
        """Advances the scanner until a stopping symbol or EOF is reached."""
        if stopping_types is None:
            stopping_types = [self.scanner.SEMICOLON, self.scanner.EOF] + self.section_keyword_strings
        while (
            self.symbol.type not in stopping_types
            and self.symbol.type != self.scanner.EOF
            and not (self.symbol.type == self.scanner.KEYWORD and self.symbol_string() in stopping_types)
        ):
            self.advance()
        if self.symbol.type == self.scanner.SEMICOLON:
            self.advance()

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
    
    def is_section_keyword(self):
        return (
            self.symbol.type == self.scanner.KEYWORD
            and self.symbol_string() in self.section_keyword_strings
        )

################################################################################
# ERROR HANDLING / MESSAGES
################################################################################

    # General error message
    def error(self, errormsg, symbol=None, synchronize = False, stopping_types=None):
        """Print a descriptive error message and increment the error count.
        Takes in error message and Symbol object (default: self.symbol) as arguments. """
        if (symbol == None):
            symbol = self.symbol
        self.error_count += 1
        if(self.error_count <= MAX_ERROR_MSGS):
            print("---------------------------------------------------------------")
            print("Error: " + errormsg) 
            print("Line " + str(symbol.line_num+1) + ", column " + str(symbol.line_pos+1)+":")
            self.scanner.print_error_line(symbol.line_num, symbol.line_pos)
            if(self.error_count == 1):
                print("Attempting to skip the affected statement(s) and continue parsing")
                print("to detect further syntax errors...")
                print("Network construction and related semantic checks will no longer be attempted. ")
        if(synchronize):
            self.synchronize(stopping_types)

    def fatal_error(self):
        """Print a message when parsing cannot safely continue due to a structural error in the file
        such as missing DEVICES/CONNECT/MONITOR keywords."""
        if(self.error_count > MAX_ERROR_MSGS):
            print("And "+str(self.error_count-MAX_ERROR_MSGS)+" more error(s)...")
            print("---------------------------------------------------------------")
        print("---------------------------------------------------------------")
        print("Parsing stopped with "+str(self.error_count)+" errors: unable to continue due to")
        print("structural error(s) in file.")
        

    def can_build_network(self):
        """Return True if network construction is still allowed."""
        return self.error_count == 0
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
            return "Input cannot be on the RHS of expression"
        if error_type == self.network.OUTPUT_TO_OUTPUT:
            return "Output cannot be on LHS of connection"
        if error_type == self.network.INPUT_CONNECTED:
            return "Input is already connected"
        if error_type == self.network.FIRST_PORT_ABSENT or error_type == self.network.SECOND_PORT_ABSENT:
            return "Port does not exist on device"
        if error_type == self.network.FIRST_DEVICE_ABSENT or error_type == self.network.SECOND_DEVICE_ABSENT:
            return "Specified name does not match a device or net"
            # When we call make_connection we check if its a net first by checking if its in the net_ids set
            # so, e.g. a typo in a net name can also lead to this error type
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
            return "Specified name does not match a device or net"
        return "Unknown monitor error"
    
    def possible_typo(self, a, b):
        """
        Return True if string a is a possible typo of string b (or vice-versa), 
        False otherwise.
        Works primarily by checking Levenshtein distance."""

        if a is None or b is None:
            return False
        if a==b:
            return False
        if a in self.section_keyword_strings and b in self.section_keyword_strings:
            # don't flag a section keyword as a typo for another section keyword
            # like MODULE and ENDMODULE
            return False
        n = len(a)
        m = len(b)
        if n > 4 and m > 4:
            if a in b or b in a:
                # should catch things like CONNECT being written as CONNECTIONS
                return True

        if n+m > 60:
            # quadratic complexity algorithm
            # don't run for performance reasons if inputs too long
            # (should rarely be the case)
            return False
        
        # Levenshtein Distance
        # Acknowledgement: Pseudocode implemented from
        # https://en.wikipedia.org/wiki/Levenshtein_distance
        # (Iterative with Full Matrix section)

        # dp[i][j] = distance between
        # first i chars of a and first j chars of b
        dp = []

        # Create 2d table of all 0s
        for i in range(n + 1):
            row = []
            for j in range(m + 1):
                row.append(0)
            dp.append(row)

        # Insertion/deletion until empty string
        for i in range(n + 1):
            dp[i][0] = i
        for j in range(m + 1):
            dp[0][j] = j

        for i in range(1, n + 1):
            for j in range(1, m + 1):
                insertion = dp[i - 1][j] + 1
                deletion = dp[i][j - 1] + 1
                substitution = dp[i - 1][j - 1] + (0 if a[i-1] == b[j-1] else 1)

                dp[i][j] = min(insertion, deletion, substitution)

        ans = dp[n][m]
        threshold = 2
        if min(n, m) <= 3:
            threshold = 1
        return ans <= threshold 
    
    def section_typo_hint(self, keyword):
        """Return a did-you-mean hint string for a possible typo of a keyword,
        if a possible typoed keyword has been recorded. 
        Return empty string otherwise."""
        if keyword not in self.possible_typo_symbols:
            return ""

        typo_symbol = self.possible_typo_symbols[keyword]
        typo_string = self.names.get_name_string(typo_symbol.id)

        return ("\n-> In line "+str(typo_symbol.line_num + 1)+", '" + typo_string + "' could be a typo. Did you mean " + keyword + "?\n")

    def name_typo_hint(self, bad_name_id, candidate_ids, candidate_description):
        """Return a did-you-mean hint if bad_name_id looks like a typo of
        one of the candidate_ids. Return empty string otherwise.
        """
        if bad_name_id is None:
            return ""

        bad_name_string = self.names.get_name_string(bad_name_id)
        for candidate_id in candidate_ids:
            candidate_name_string = self.names.get_name_string(candidate_id)
            if self.possible_typo(bad_name_string, candidate_name_string):
                return ("\n-> Did you mean " + candidate_description+ " '"+ candidate_name_string+ "'?\n")
        
        return ""

    def signal_name_typo_hint(self, bad_name_id):
        """Return a did-you-mean hint for a top-level signal/device/net/module instance name, or an empty 
        string if no good candidate signal name exists."""
        device_ids = []
        for device in self.devices.devices_list:
            device_ids.append(device.device_id)

        hint = self.name_typo_hint(bad_name_id, device_ids, "device")
        if hint == "":
            hint = self.name_typo_hint(bad_name_id, self.net_ids, "net")
        if hint == "":
            hint = self.name_typo_hint(bad_name_id, self.module_instance_ids, "module instance")
        return hint

    def module_signal_name_typo_hint(self, bad_name_id, module_definition):
        """Return a did-you-mean hint for a signal name inside a module definition, or an empty
        string if no good candidate signal name exists. """
        hint = self.name_typo_hint(bad_name_id, module_definition.device_ids, "module device")
        if hint == "":
            hint = self.name_typo_hint(bad_name_id, module_definition.net_ids, "module net")
        if hint == "":
            module_port_ids = module_definition.input_ids.union(module_definition.output_ids)
            hint = self.name_typo_hint(bad_name_id, module_port_ids, "module port")
        return hint

#############################################################################################
# PARSING HELPER FUNCTIONS
#############################################################################################

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

    
#############################################################################################
# EBNF PARSING: BASIC EBNF RULES
#############################################################################################

    def parse_name(self, consume_reserved_keyword=False, expected_name=None):
        """Parse a name (i.e. check if the current symbol is a scanner.NAME) 
        and return the Symbol object if successful, or None otherwise.

        Displays an error if a reserved keyword is seen instead of a name.
        Optionally, can choose to consume the reserved keyword,
        which can be useful for recovering from a reserved keyword used 
        in a statement like a name_list. Avoid setting this option in situations
        outside of a name list statement, e.g. when we want to parse
        the module name, where it may cause structural issues to be missed.
        
        Optional expected_name paraneter allows provide better error message context.

        """
        # We return the symbol object, not just the id, so we maintain information about the
        # symbol's location, this will be helpful for error messages.
        if self.symbol.type == self.scanner.NAME:
            name_symbol = self.symbol
            self.advance()  # consume the name
            return name_symbol

        else:
            if expected_name is None:
                expected_name = "a name"
            # store the bad symbol in case we advance 
            bad_symbol = self.symbol
            errormsg = "Expected " + expected_name
            if self.symbol.type == self.scanner.NUMBER:
                errormsg += ", but names cannot start with a number."

            elif self.symbol.type == self.scanner.KEYWORD:
                errormsg += ", but got a reserved keyword: "
                errormsg += self.symbol_string()

                if consume_reserved_keyword:
                    self.advance()

            else:
                errormsg += "."

            self.error(errormsg, bad_symbol, synchronize=True)

        return None

    def parse_name_list(self, expected_name=None):
        """Parse name_list based on EBNF specification.
        name_list = name, { ',', name }.
        Optional expected_name field for the type of name expected in the list,
        for better error message context in parse_name. 
        Return list of symbol objects if successful, None otherwise"""

        name_list = []

        name_symbol = self.parse_name(consume_reserved_keyword=True, expected_name=expected_name)
        if name_symbol is not None:
            name_list.append(name_symbol)

        while self.symbol.type == self.scanner.COMMA:
            self.advance()

            name_symbol = self.parse_name(consume_reserved_keyword=True, expected_name=expected_name)
            if name_symbol is None:
                continue
            name_list.append(name_symbol)
        
        if len(name_list) == 0:
            return None

        return name_list

    def parse_signal(self):
        """Parse signal or literal based on EBNF specification:
         signal = name, [ '.', name ]
         literal = 0 | 1

         return Signal object if successful (with is_literal=True for literals), None otherwise."""
        
        # 0 or 1 should be a literal
        if self.symbol.type == self.scanner.NUMBER:
            literal_symbol = self.symbol
            value = self.symbol.id

            if value not in [0, 1]:
                self.error("Only 0 or 1 can be used as a signal literal",literal_symbol, synchronize=True)
                return None

            self.advance()
            return Signal(main_symbol=literal_symbol, port_symbol=None, is_literal=True, literal_value=value)

        name_symbol = self.parse_name(expected_name="signal name", consume_reserved_keyword=True)
        if name_symbol is None:
            return None

        if self.symbol.type == self.scanner.DOT:
            self.advance()

            port_symbol = self.parse_name(expected_name="port name", consume_reserved_keyword=True)
            if port_symbol is None:
                return None

            return Signal(main_symbol=name_symbol, port_symbol=port_symbol)
        return Signal(main_symbol=name_symbol, port_symbol=None)

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

    def parse_connection_statement(self):
        """Parse:
            signal_list, '=', source, ';'
            source = signal | literal

        Return:
            (input_signal_list, output_signal)
            or None on error.

        If None is returned, this function must have either consumed the
        malformed statement and synchronized to a section keyword/EOF, or otherwise
        made enough progress for the enclosing section parser to continue safely.
        """
        input_signal_list = self.parse_signal_list()
        if input_signal_list is None:
            return None
        if self.symbol.type != self.scanner.EQUALS:
            errormsg = "Expected '=' in connection"
            errormsg += self.section_typo_hint("MONITOR")
            self.error(errormsg, synchronize=True)
            
            return None
        self.advance()

        output_signal = self.parse_signal()
        if output_signal is None:
            return None

        if self.symbol.type != self.scanner.SEMICOLON:
            if self.symbol.type == self.scanner.COMMA:
                self.error(
                    "RHS of connection statement can only have one signal",
                    synchronize=True,
                )
            else:
                self.error("Expected semicolon after connection", synchronize=True)
            return None

        self.advance()
        return input_signal_list, output_signal

    def parse_device_kind(self):
        """Parse device_kind in the EBNF:
        parametrised_device, \"(\", number, \")\",
        or fixed_device. 

        Return a tuple containing ("module" or "primitive", device_kind_id, device_parameter),
        where device_kind_id is the name ID for the device string like "AND"
        and device_parameter is a plain integer, like 2 for AND(2),
         or return None if there's an error. """

        # When called should point to the symbol for the device keyword (like AND, SWITCH)

        if self.symbol.type == self.scanner.NAME: 
            # Then it should be a module name 
            module_name_string = self.names.get_name_string(self.symbol.id)

            if module_name_string in self.module_definitions or not self.can_build_network():
                                                                # if we can't build the network, syntax check only
                module_name_id = self.symbol.id
                self.advance()
                # Now we're pointing at the next symbol 
                # check that it's not ( for a more helpful error message
                # (otherwise we get error message expected a name)
                if self.symbol.type == self.scanner.L_BRACKET:
                    self.error("Module type should not have parentheses", synchronize=True)
                    return None
                return "module", module_name_id, None
                
            errormsg = "Expected primitive device type (e.g. AND) or previously-defined module name"
            if(self.device_exists(self.symbol)):
                errormsg += "\nAre you trying to connect a device? This should be done in the CONNECT section."
                errormsg += self.section_typo_hint("CONNECT")
            self.error(errormsg, synchronize=True)
            return None
        
        if self.is_parameterised_device():
            device_kind_id = self.symbol.id

            self.advance()  # consume the device type like AND
            if self.symbol.type != self.scanner.L_BRACKET:
                self.error("Expected '(' after parameterised device", synchronize=True)
                return None
            self.advance()  # consume (

            if self.symbol.type != self.scanner.NUMBER:
                self.error("Expected number", synchronize=True)
                return None
            device_parameter = self.symbol.id
            self.advance()  # consume the number

            if self.symbol.type != self.scanner.R_BRACKET:
                self.error("Expected ')'", synchronize=True)
                return None

            self.advance()  # consume )
            return "primitive", device_kind_id, device_parameter

        if self.is_fixed_device():
            device_kind_id = self.symbol.id
            self.advance()  # consume the device type like XOR
            return "primitive", device_kind_id, None

        self.error("Invalid device kind.", synchronize=True)
        return None
    
    def parse_device_statement(self):
        """Parse:
            device_kind, name_list, ';'

        Return:
            (device_kind_symbol, device_kind_result, device_names)
            or None on error.
        """

        device_kind_symbol = self.symbol

        device_kind_result = self.parse_device_kind()
        if device_kind_result is None:
            return None

        device_names = self.parse_name_list(expected_name="device name")
        if device_names is None:
            if self.symbol.type == self.scanner.SEMICOLON:
                self.advance()
            else:
                self.synchronize()
            return None

        if self.symbol.type != self.scanner.SEMICOLON:
            errormsg = "No semicolon found after device definition (or comma to separate device names)"

            if self.symbol.type == self.scanner.EQUALS:
                errormsg += "\nDevice declarations cannot use '='."
                errormsg += "\nThis may be a connection statement in the wrong section."
                errormsg += "\nDid you forget the CONNECT section keyword?"
                errormsg += self.section_typo_hint("CONNECT")

            elif self.symbol.type == self.scanner.DOT:
                errormsg += "\nDevice declarations cannot use ports like '.I1'."
                errormsg += "\nThis may be a connection statement in the wrong section."
                errormsg += "\nDid you forget the CONNECT section keyword?"
                errormsg += self.section_typo_hint("CONNECT")

            self.error(errormsg, synchronize=True)
            return None

        self.advance()
        return device_kind_symbol, device_kind_result, device_names
    
#############################################################################################
# PARSING NETS AND NET HELPER FUNCTIONS
#############################################################################################

    def is_net(self, signal):
        return (not signal.is_literal 
                and signal.main_id in self.net_ids 
                and signal.port_id is None)
    
    def net_used_with_port(self, signal):
        """Return True if signal uses a declared net name with a port."""
        return (
            not signal.is_literal 
            and signal.main_id in self.net_ids
            and signal.port_id is not None)

    def parse_net_declaration(self):
        """Parse a net declaration statement:
          name_list, ';'."""
        
        # 1. EBNF based syntax and collect the names of the nets 
        net_symbols = self.parse_name_list(expected_name="net name")

        if net_symbols is None:
            if self.symbol.type == self.scanner.SEMICOLON:
                self.advance()
            else:
                self.synchronize()
            return True

        if self.symbol.type != self.scanner.SEMICOLON:
            errormsg = "Expected semicolon after net declaration or comma to separate a list of nets."
            if self.is_keyword_name("CONNECT"):
                errormsg += "\nThe NETS declaration may be malformed or missing a semicolon before CONNECT."
            if(self.symbol.type == self.scanner.EQUALS):
                errormsg += "\nThis looks like a connection statement. Did you forget the CONNECT section?"
                errormsg += self.section_typo_hint("CONNECT")
                self.error(errormsg)
                return False # prevent potential long cascade if we're probably in the wrong section
            elif self.symbol.type == self.scanner.DOT:
                errormsg =  "Net declaration cannot have a port. Is this meant to be a"
                errormsg += "\nconnection statement? The CONNECT section keyword might be missing."
                errormsg += self.section_typo_hint("CONNECT")
                self.error(errormsg)
                return False # prevent potential long cascade if we're probably in the wrong section
            self.error(errormsg, synchronize=True)
            return True

        self.advance()

        # 2. Semantic checks and create the actual nets.

        if not self.can_build_network():
            return True

        for net_symbol in net_symbols:
            if self.device_exists(net_symbol):  # if a device already exists with the same name/id
                # n.b. we dont need checks the other way (i.e. device name conflicts with net name)
                # since device section is always before the nets section. 
                self.error("Net name conflicts with an existing device name", net_symbol)
                continue 
            
            net_id = net_symbol.id
            # keep track of existing nets

            if net_id in self.module_instance_ids:
                self.error("Net name conflicts with an existing module instance name", net_symbol)
                continue

            if net_id in self.net_ids:
                self.error("Net has already been declared", net_symbol)
                continue
            self.net_ids.add(net_id)

        return True
    
    def parse_nets(self):
        """Parse the NETS section.
        Return True if successful and False otherwise. """
        while True:
            if self.is_keyword_name("CONNECT"): # end of NETS section. 
                return True
            
            if(self.is_section_keyword()):
                errormsg = "Unexpected section keyword after NETS section - it should be followed by CONNECT section."
                errormsg += self.section_typo_hint("CONNECT")
                self.error(errormsg)
                return False

            if self.symbol.type == self.scanner.EOF:
                errormsg = "Unexpected end of file in NETS section - it should be followed by CONNECT section."
                errormsg += self.section_typo_hint("CONNECT")
                self.error(errormsg)                
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
                driver_net_id = driver.main_id
                if driver_net_id in seen_net_ids:
                    self.error("Circular definition of nets detected", driver.main_symbol)
                    return False

                if driver_net_id not in self.net_driver_dict:
                    self.error("Net has no driver", driver.main_symbol)
                    return False

                seen_net_ids.add(driver_net_id)
                driver = self.net_driver_dict[driver_net_id]
            self.net_driver_dict[net_id] = driver

        return True

#############################################################################################
# HELPER FUNCTIONS FOR LITERALS
#############################################################################################

    def get_or_create_const_switch(self, signal):
        """Return Signal object for artificial SWITCH(0) or SWITCH(1) used for literals."""
        # When there is a literal in the code like 0 or 1,
        # We create artificial SWITCH(0) and SWITCH(1) with an internal
        # switch name @LITERAL_0 or @LITERAL_1
        # and use that to provide the literal signal.

        if not self.can_build_network():
            return None
        
        if not signal.is_literal:
            self.error("Internal error: get_or_create_const_switch called on a non-literal signal", signal.main_symbol)

        value = signal.literal_value
        

        if value == 0:
            const_name = "@LITERAL_0"
        elif value == 1:
            const_name = "@LITERAL_1"
        else:
            self.error("Only 0 or 1 can be used as a signal literal", signal.main_symbol)
            return None

        # Get the ID in the names dict for @LITERAL_0/1 (or make new ID for it)
        const_device_id = self.names.lookup([const_name])[0]

        # if we had already made the device, we just return it
        if self.devices.get_device(const_device_id) is not None:
            return const_device_id

        error_type = self.devices.make_device(
            const_device_id,
            self.devices.SWITCH,
            value,
        )

        error_message = self.device_error_message(error_type)
        if error_message is not None:
            print("Internal Error: unexpected error when creating literal switch:") # This should never happen
            self.error(error_message, signal.main_symbol)
            return None

        return const_device_id
    
#############################################################################################
# MODULE PARSING AND STORING ModuleDefinition
#############################################################################################

    # Input and output sections ################################################

    def parse_module_ports_list(self):
        """
        Parse a list of module ports. 
        
        Return the list of signals if successful, and None if unsuccessful.
        If unsuccessful, synchronizes past the ';' after the ports list statement. 
        """

        if self.is_section_keyword() or self.symbol.type == self.scanner.EOF:
            return None
        
        ports_list = self.parse_name_list(expected_name="module port name")
        if ports_list is None:
            if self.symbol.type == self.scanner.SEMICOLON:
                self.advance()
            else:
                self.synchronize()

            return None
        


        if self.symbol.type != self.scanner.SEMICOLON:

            errormsg = "Expected semicolon after module's port list or comma in between list entries."
            if self.is_keyword_name("OUTPUTS"):
                errormsg += "\nThe INPUTS port list may be malformed or missing a semicolon before OUTPUTS."
            elif self.is_keyword_name("DEVICES"):
                errormsg += "\nThe OUTPUTS port list may be malformed or missing a semicolon before DEVICES."
            else:
                errormsg += self.section_typo_hint("OUTPUTS")
                errormsg += self.section_typo_hint("DEVICES")

            self.error(errormsg, synchronize=True)

            return None

        self.advance()
        return ports_list

    def parse_module_inputs_list(self):
        """
        Parse the full list of module inputs (which can be split into multiple statements). 

        Return the list of symbols if successful, an empty list if there are no valid ports, 
        or None if there's a structural error that should abandon attempts to build
        the module definition. 
        """
        if not self.is_keyword_name("INPUTS"):
            self.error("Expected INPUTS section in module definition")
            return None
        self.advance()
        
        inputs_list = []
        while not self.is_keyword_name("OUTPUTS"):

            if self.symbol.type == self.scanner.EOF or self.is_section_keyword():
                errormsg = "Incorrect module definition structure - INPUTS section should be followed by OUTPUTS section."
                errormsg += self.section_typo_hint("OUTPUTS")
                self.error(errormsg)
                return None
            ports_list = self.parse_module_ports_list()
            if ports_list is None:
                if self.is_keyword_name("OUTPUTS"):
                    # we recovered to the next section already so should stop 
                    break
                return None
            inputs_list.extend(ports_list)
        return inputs_list

    def parse_module_outputs_list(self):
        """
        Parse the full list of module outputs (which can be split into multiple statements). 
        
        Return the list of symbols if successful, an empty list if there are no valid ports, 
        or None if there's a structural error that should abandon attempts to build
        the module definition. """
        if not self.is_keyword_name("OUTPUTS"):
            self.error("Expected OUTPUTS section in module definition", synchronize=True)
            return None
        self.advance()

        outputs_list = []
        while not self.is_keyword_name("DEVICES"):
            if self.symbol.type == self.scanner.EOF or self.is_section_keyword():
                errormsg = "Incorrect module definition structure - OUTPUTS section should be followed by DEVICES section"
                errormsg += self.section_typo_hint("DEVICES")
                self.error(errormsg)
                return None
            ports_list = self.parse_module_ports_list()
            if ports_list is None:
                if self.is_keyword_name("DEVICES"):
                    # we recovered to the next section already so should stop 
                    break
                return None
            outputs_list.extend(ports_list)
        return outputs_list

    
    # DEVICES section within module #############################################
    
    def parse_module_device(self, module_definition):
        """Parse a single device instantiation (primitive or module) inside a 
        module's DEVICES section.
        Return True if section was parsed and consumed getting lost
        (regardless of semantic correctness), False otherwise"""
        
        device_statement_result = self.parse_device_statement()
        if device_statement_result is None:
            return True
        _device_kind_symbol, device_kind_result, device_name_list = device_statement_result

        for device_symbol in device_name_list:
            device_id = device_symbol.id
            if device_id in module_definition.device_ids:
                self.error("Device name already used in this module", device_symbol)
                continue
            if device_id in module_definition.input_ids or device_id in module_definition.output_ids:
                # The device name is the same as something in INPUTS or OUTPUTS of the module.
                self.error("Module device name conflicts with an input/output port name", device_symbol )
                continue
            
            # Create the ModuleDevice object in the ModuleDefinition
            module_definition.device_ids.add(device_id)
            module_definition.devices.append(
                ModuleDevice(
                    device_symbol,
                    device_kind_result[0],  # "primitive" or "module"
                    device_kind_result[1],  # primitive kind name (e.g. XOR) or module name symbol
                    device_kind_result[2],  # primitive parameter (e.g. input size), or None for module
                )
            )

        return True
    
    def parse_module_devices(self, module_definition):
        
        while True:
            
            if (self.is_keyword_name("NETS") or self.is_keyword_name("CONNECT")):
                return True
            if self.symbol.type == self.scanner.EOF or self.is_section_keyword():
                errormsg = "Incorrect module definition structure: module DEVICES section should be followed by NETS or CONNECT section"
                errormsg += self.section_typo_hint("NETS")
                errormsg += self.section_typo_hint("CONNECT")
                self.error(errormsg)
                return False
            self.parse_module_device(module_definition)
        return
    
    # NETS section within module ##################################################
    
    def parse_module_net_declaration(self, module_definition):
        net_symbols = self.parse_name_list("module net name")

        if net_symbols is None:
            if self.symbol.type == self.scanner.SEMICOLON:
                self.advance()
            else:
                self.synchronize()
            return True

        if self.symbol.type != self.scanner.SEMICOLON:
            errormsg = "Expected semicolon after net declaration or comma to separate a list of nets."
            if(self.symbol.type == self.scanner.EQUALS):
                errormsg += "\nThis looks like a connection statement. Did you forget the CONNECT section?"
                errormsg += self.section_typo_hint("CONNECT")
                self.error(errormsg)
                return False # prevent potential long cascade if we're probably in the wrong section
            elif self.symbol.type == self.scanner.DOT:
                errormsg =  "Net declaration cannot have a port. Is this meant to be a"
                errormsg += "\nconnection statement? The CONNECT section keyword might be missing."
                errormsg += self.section_typo_hint("CONNECT")
                self.error(errormsg)
                return False # prevent potential long cascade if we're probably in the wrong section
            self.error(errormsg, synchronize=True)
            return True

        self.advance()

        if not self.can_build_network():
            return True

        for net_symbol in net_symbols:
            net_id = net_symbol.id
            if net_id in module_definition.device_ids:
                self.error("Module net name conflicts with a device name", net_symbol)
                continue
            if net_id in module_definition.input_ids or net_id in module_definition.output_ids:
                self.error("Module net name conflicts with a port name", net_symbol)
                continue
            if net_id in module_definition.net_ids:
                self.error("Module net has already been declared", net_symbol)
                continue
            
            # module_data is a ModuleDefinition object, passed by reference to this function
            # created initially in parse_module_definition(). 
            module_definition.net_ids.add(net_id)

        return True

    
    def parse_module_nets(self, module_definition):
        while True:
            if self.is_keyword_name("CONNECT"):
                return True
            
            if self.is_section_keyword():
                errormsg = "Incorrect module definition structure - NETS section should be followed by CONNECT section"
                errormsg += self.section_typo_hint("CONNECT")
                self.error(errormsg)
                return False

            if self.symbol.type == self.scanner.EOF:
                errormsg = "Unexpected end of file in module NETS section"
                errormsg += self.section_typo_hint("CONNECT")
                self.error(errormsg)
                return False

            if not self.parse_module_net_declaration(module_definition):
                return False
        
            
    def flatten_module_net_driver_dict(self, module_definition):
        for net_id in list(module_definition.net_driver_dict.keys()):
            seen_net_ids = {net_id}
            driver = module_definition.net_driver_dict[net_id]
            while self.is_module_net(driver, module_definition):
                driver_net_id = driver.main_id
                if driver_net_id in seen_net_ids:
                    self.error("Circular definition of module nets detected", driver.main_symbol)
                    return False

                if driver_net_id not in module_definition.net_driver_dict:
                    self.error("Module net has no driver", driver.main_symbol)
                    return False

                seen_net_ids.add(driver_net_id)
                driver = module_definition.net_driver_dict[driver_net_id]

            module_definition.net_driver_dict[net_id] = driver
        return True
    
    # CONNECT section within module ###############################################

    def is_module_net(self, signal, module_definition):
        return not signal.is_literal and signal.main_id in module_definition.net_ids and signal.port_id is None

    def module_net_used_with_port(self, signal, module_definition):
        return not signal.is_literal and signal.main_id in module_definition.net_ids and signal.port_id is not None
    
    def is_module_output_port(self, signal, module_definition):
        return (
            not signal.is_literal
            and signal.port_id is None
            and signal.main_id in module_definition.output_ids
        )
    
    def is_module_input_port(self, signal, module_definition):
        return (
            not signal.is_literal
            and signal.port_id is None
            and signal.main_id in module_definition.input_ids
        )
    
    def is_module_port(self, signal, module_definition):
        # Used for within a module definition.
        # If checking if a signal is a port of a module instance in the
        # main circuit, use is_module_instance_port. 
        return (
            self.is_module_input_port(signal, module_definition)
            or 
            self.is_module_output_port(signal, module_definition)
        )

    def module_port_used_with_port(self, signal, module_definition):
        return (not signal.is_literal and 
            ( 
                signal.main_id in module_definition.input_ids
                or signal.main_id in module_definition.output_ids
            )
            and signal.port_id is not None
        )
    
    def parse_module_connect(self, module_definition):
        """
        Parse a connection statement within a module.
        Create the connection if there are no errors in the network so far. 
        Return True if parser consumes the whole section, False otherwise
        """
        
        # 1. Parse the device EBNF rule (syntax)

        connection_statement = self.parse_connection_statement()
        if connection_statement is None:
            return True # parse_connection_statement guarantees progress before returning None
        input_signal_list, output_signal = connection_statement

        if not self.can_build_network():
            return True

        # 2. Store the connections to be made, and some net semantic checks
        #     (other semantic checks performed during resolve_and_create_connections)

        if self.module_net_used_with_port(output_signal, module_definition):
            self.error("Net cannot have a port", output_signal.port_symbol)
            return True
        if self.module_port_used_with_port(output_signal, module_definition):
            errormsg = ("Module input/output port should not have a pin like '." + 
                        self.names.get_name_string(output_signal.port_symbol.id)+ "'")
            self.error(errormsg, output_signal.port_symbol)
            return True
        if self.is_module_output_port(output_signal, module_definition):
            self.error("Module output port cannot be used as a source inside the module definition", output_signal.main_symbol)
            return True
        if (
            not output_signal.is_literal
            and output_signal.main_id not in module_definition.input_ids
            and output_signal.main_id not in module_definition.output_ids
            and output_signal.main_id not in module_definition.net_ids
            and output_signal.main_id not in module_definition.device_ids
        ):
            errormsg = "Signal name has not been declared in this module"
            errormsg += self.module_signal_name_typo_hint(output_signal.main_id, module_definition)
            self.error(errormsg, output_signal.main_symbol)
            return True            

        # n.b. here "input signal" can refer to the output port of the module definition
        # since internally (within the module) we drive the output port. 
        for input_signal in input_signal_list:
            if not self.can_build_network():
                return True
            # If the LHS is a net, we store its RHS in net_driver_dict
            # (RHS can also be a net, this will be flattened with a call
            # to flatten_net_driver_dict during resolve_and_create_connections)
            if self.module_net_used_with_port(input_signal, module_definition):
                self.error("Net cannot have a port", input_signal.port_symbol)
                continue
            
            if self.module_port_used_with_port(input_signal, module_definition):
                errormsg = "Module input/output port should not have a pin like '."+self.names.get_name_string(input_signal.port_symbol.id)+"'"
                self.error(errormsg, input_signal.port_symbol) 
                continue
            
            if input_signal.is_literal:
                self.error("Literal (0 or 1) cannot be on LHS of expression", input_signal.main_symbol)
                continue
            
            if (
                input_signal.main_id not in module_definition.input_ids
                and input_signal.main_id not in module_definition.output_ids
                and input_signal.main_id not in module_definition.net_ids
                and input_signal.main_id not in module_definition.device_ids
            ):
                errormsg = "Signal name has not been declared in this module"
                errormsg += self.module_signal_name_typo_hint(input_signal.main_id, module_definition)
                self.error(errormsg, input_signal.main_symbol)
                continue

            # Here we treat the module input/output ports like nets. 
            if (self.is_module_net(input_signal, module_definition) or
                self.is_module_port(input_signal, module_definition)):

                net_id = input_signal.main_id
                if input_signal.main_id in module_definition.input_ids:
                    # an input port to the module should be driven from outside - it should NOT be 
                    # driven within the module 
                    self.error("Module input port cannot be driven inside the module", input_signal.main_symbol)
                    continue
                if(net_id not in module_definition.net_driver_dict):
                    module_definition.net_driver_dict[net_id] = output_signal
                else:
                    if self.is_module_net(input_signal, module_definition):
                        self.error("Net has multiple drivers", input_signal.main_symbol)
                    else: 
                        self.error("Module port has multiple drivers", input_signal.main_symbol)
                    continue
                
            # Otherwise if LHS is a regular signal we just add it to the 
            # pending connections list. 
            else:
                module_definition.connections.append((input_signal, output_signal))

        return True
    
    def parse_module_connections(self, module_definition):
        while True:
            if self.is_keyword_name("ENDMODULE"):
                return True

            if self.symbol.type == self.scanner.EOF or self.is_section_keyword():
                errormsg = "Incorrect module definition structure: CONNECT section should be followed by ENDMODULE"
                errormsg += self.section_typo_hint("ENDMODULE")
                self.error(errormsg)
                return False

            if not self.parse_module_connect(module_definition):
                return False
                    
    # Overall module definition ####################################################

    def discard_invalid_module_definition(self, module_name_string, sync_to_module_end=False):
        """Display an error message stating that the module definition is invalid,
        and synchronize to the end of the module definition if sync_to_module_end is True.
        Return True if sucessfully synchronized to the end of a module definition, False otherwise.
        """

        # in parse_module_definition, we call this. 
        # if this returns False, we're hopelessly lost and
        # should therefore cause a fatal error. If it's True, 
        # we still don't store the ModuleDefinition but we can continue
        # syntax checks without a fatal error, because at least we know
        # where we are in the file. 
        print("---------------------------------------------------------------")
        print("Module definition for "+module_name_string+" is invalid due to the above error(s).\n")            
        if(sync_to_module_end):
            self.synchronize(["ENDMODULE"])
            if(self.symbol.type == self.scanner.EOF):
                return False
            self.advance()
            if(self.symbol.type != self.scanner.SEMICOLON):
                self.error("Missing semicolon after ENDMODULE")
            else:
                self.advance()
            if self.is_keyword_name("DEVICES") or self.is_keyword_name("MODULE"):
                return True
            else:
                self.error("Expected DEVICES section or new MODULE definition.")
                return False
        return True


    def parse_module_definition(self):
        """Parse a single module definition block. The module definition is 
        stored as a ModuleDefinition object if successful. 
        
        Return True if it was able to parse to the end of the module definition (after ENDMODULE;), 
        regardless if there were errors. 
        Return False if we weren't able to parse to the end of the module definition,
        usually due to a structural error causing the parser to become lost.  """
        
        # We want to store the ModuleDefinition only if the module 
        # has no errors. Hence we store the error_count at the start
        # of parsing the module. If it increased, we know the ModuleDefinition
        # should not be stored - can keep parsing the rest of the file
        # but trying to instantiate this module will fail. 
        module_starting_error_count = self.error_count 
        
        self.advance()  # consume the MODULE symbol

        module_name_symbol = self.parse_name(expected_name="module name after 'MODULE'") 
        if module_name_symbol is None:
            return False
        
        module_name_string = self.names.get_name_string(module_name_symbol.id)

        if module_name_string in self.module_definitions:
            self.error("A module type with this name already exists", module_name_symbol)
        
        module_input_symbols = self.parse_module_inputs_list()
        if module_input_symbols is None:
            return self.discard_invalid_module_definition(module_name_string, True)           

        module_output_symbols = self.parse_module_outputs_list()
        if module_output_symbols is None:
            return self.discard_invalid_module_definition(module_name_string, True)           
        
        # Check for duplicate input port names
        seen_input_ids = set()
        for input_symbol in module_input_symbols:
            if input_symbol.id in seen_input_ids:
                self.error("Duplicate module input port name", input_symbol)
                continue
            seen_input_ids.add(input_symbol.id)

        # Check for duplicate output port names
        seen_output_ids = set()
        for output_symbol in module_output_symbols:
            if output_symbol.id in seen_output_ids:
                self.error("Duplicate module output port name", output_symbol)
                continue
            if output_symbol.id in seen_input_ids:
                self.error("Module port cannot be both input and output", output_symbol)
                continue    
            seen_output_ids.add(output_symbol.id)
               

        module_definition = ModuleDefinition(module_name_symbol, module_input_symbols, module_output_symbols)

        # The following function calls add to the module_definition (which is passed as parameter)
        # to add all the ModuleDevice and ModuleConnections. 

        if not self.is_keyword_name("DEVICES"):
            self.error("Expected DEVICES section in module")
            return self.discard_invalid_module_definition(module_name_string, True)           
        self.advance() 

        if not self.parse_module_devices(module_definition):
            return self.discard_invalid_module_definition(module_name_string, True)           

        if self.is_keyword_name("NETS"):
            self.advance()
            if not self.parse_module_nets(module_definition):
                return self.discard_invalid_module_definition(module_name_string, True)

        if not self.is_keyword_name("CONNECT"):
            self.error("Expected CONNECT section in module")
            return self.discard_invalid_module_definition(module_name_string, True)           
        self.advance()

        if not self.parse_module_connections(module_definition):
            return self.discard_invalid_module_definition(module_name_string, True)

        if not self.is_keyword_name("ENDMODULE"):
            self.error("Expected ENDMODULE after module body")
            return self.discard_invalid_module_definition(module_name_string, True)
        self.advance()
        if self.symbol.type != self.scanner.SEMICOLON:
            self.error("No semicolon found after ENDMODULE")
        else:
            self.advance() # consume ;

        if module_starting_error_count > 0:
            # Only doing syntax checks
            return True

        if self.error_count > module_starting_error_count:
            self.discard_invalid_module_definition(module_name_string, False)
            return True

        if not self.flatten_module_net_driver_dict(module_definition):
            return True 
        
        
        
        # After flattening, go through and check all module outputs are driven
        for output_symbol in module_definition.output_symbols:
            if output_symbol.id not in module_definition.net_driver_dict:
                self.error("Module output has no driver", output_symbol)
                continue
        if self.error_count > module_starting_error_count:
            self.discard_invalid_module_definition(module_name_string, False)
            return True

        self.module_definitions[module_name_string] = module_definition
        return True

#############################################################################################
# MODULE INSTANTIATION
#############################################################################################   

    # Helpers 
    
    def make_internal_name_id_from_instance_id(self, instance_id, local_id):
        # input instance_id is the id of the module instance within which
        # a device, connect, or sub-module with instance local_id is being instantiated. 
        # returns an id for "instance_name->local_name"
        #
        instance_name = self.names.get_name_string(instance_id)
        local_name = self.names.get_name_string(local_id)
        internal_name = instance_name + "->" + local_name
        return self.names.lookup([internal_name])[0]

    def map_module_signal_to_instance_signal(self, signal, instance_id):
        """Map a signal inside a module definition to the corresponding signal
        inside one module instance.
        """
        # Basically in a module definition currenty we're just storing the signals as Signal
        # for example device X1.I1 in a half adder module H1 is just stored with
        # Signal(main_symbol = Symbol(X1), port_symbol = Symbol(I1))
        # Here we create a new Signal using the internal main_id, which is, e.g. H1->X1.I1
        # Thus, we still have the Symbol for X1 and I1 which we can point to for error messages
        # but we now have a new internal main_id so different instances of the module
        # have separate signals.

        if signal.is_literal:
            return signal

        internal_main_id = self.make_internal_name_id_from_instance_id(
            instance_id,
            signal.main_id,
        )

        return Signal(
            main_symbol=signal.main_symbol,
            port_symbol=signal.port_symbol,
            is_literal=False,
            literal_value=None,
            main_id=internal_main_id,
            port_id=signal.port_id,
        )
    
    def is_module_instance_port(self, signal):
        return (
            not signal.is_literal
            and signal.port_id is not None
            and (signal.main_id, signal.port_id) in self.module_instance_ports
        )
    
    def instantiate_module(self, instance_symbol, module_name_id, instance_id):
        """Actually instantiate the module. 
        Takes in symbol of the instance name and the module name id"""

        # We make all the input and output ports of a module and the 
        # nets inside the module instance
        # into nets with an "internal" name, of the form
        # INSTANCENAME->PORT/NET NAME
        # We also create devices with the relevant internal name 
        # and use pre-existing nets/devices functionality to build
        # all the devices and connections in the module. 

        # field instance_id  - this is because now we have
        # modules inside modules, say we can have
        # module FA (full adder), instantiating module HA
        # The internal names for things in the HA should become
        # FA1->HA->X1, FA2->HA->X1
        # So we want to be able to modify the instance_id to store
        # these internal names like FA1->HA->something, without actually modifying
        # instance_symbol.id (in the module's definition). i.e. We dont want to 
        # change HA into FA1->HA in the definition, but we still want to keep track
        # that this instance_id should be FA1->H1

        # EVERYTHING should now use instance_id, except for keeping track of
        # instance_symbol for the purpose of error messages. 

        # 1. Check that the instance name is valid

        module_name = self.names.get_name_string(module_name_id)
        module_definition = self.module_definitions[module_name]

        if instance_id in self.module_instance_ids: # note to self: had to change these
                                                    # to use instance_id not instance_symbol.id
                                                    # since otherwise FA1.H1 and FA2.H1 conflict
                                                    # because we're only checking H1
            self.error("Module instance with this name already exists", instance_symbol)
            return False

        if self.devices.get_device(instance_id) is not None:
            self.error("Module instance name conflicts with an existing device", instance_symbol)
            return False

        if instance_id in self.net_ids:
            # Likely unnecessary check because DEVICES is before NETS...
            self.error("Module instance name conflicts with an existing net", instance_symbol)
            return False

        # Add the instance id to the set for future duplicate detection
        self.module_instance_ids.add(instance_id)

        # 2. Create all the nets and signals corresponding to
        #    the module instance's input and output ports

        for input_id in module_definition.input_ids:
            # get the internal net id, by adding the internal name
            # (e.g. H1->A) to the name table
            # we use the instance_id for this call, the full FA1->HA->A instead of just HA->A
            internal_input_id = self.make_internal_name_id_from_instance_id(instance_id, input_id)
            # create the net
            self.net_ids.add(internal_input_id)

            # keep track of the signal as a module input
            # e.g. module_instance_ports[(H1, A)] for instance name H1, input A
            self.module_instance_ports[(instance_id, input_id)] = Signal(
                main_symbol=instance_symbol,
                port_symbol=None,
                main_id=internal_input_id,
                port_id=None,
            )
            self.module_instance_port_directions[(instance_id, input_id)] = "input"

        for output_id in module_definition.output_ids:
            # get the internal net id, by adding the internal name
            # (e.g. H1->A) to the name table
            internal_output_id = self.make_internal_name_id_from_instance_id(instance_id, output_id)
            # create the net
            self.net_ids.add(internal_output_id)

            # keep track of the signal as a module output
            # e.g. module_instance_ports[(H1, SUM)] for instance name H1, output SUM
            self.module_instance_ports[(instance_id, output_id)] = Signal(
                main_symbol=instance_symbol,
                port_symbol=None,
                main_id=internal_output_id,
                port_id=None,
            )
            self.module_instance_port_directions[(instance_id, output_id)] = "output"

        # 3. Create the module instance's nets 
        for module_net_id in module_definition.net_ids:
            internal_net_id = self.make_internal_name_id_from_instance_id(instance_id, module_net_id)
            self.net_ids.add(internal_net_id)

        # 4. Create the devices for the module instance
        for module_device in module_definition.devices:
            if module_device.kind_type == "module":
                # nested modules

                nested_instance_id = self.make_internal_name_id_from_instance_id(instance_id, module_device.symbol.id)
                 
                # Recursive call to instantiate_module. 
                # e.g. current instance_id corresponds to FA1
                # nested_instance_id is thus FA1->HA
                if not self.instantiate_module(
                    module_device.symbol,
                    module_device.kind_name,
                    instance_id=nested_instance_id):
                    continue
                
            elif module_device.kind_type == "primitive":
                internal_device_id = self.make_internal_name_id_from_instance_id(instance_id, module_device.symbol.id)

                # Create the device with the internal id
                error_type = self.devices.make_device(
                    internal_device_id,
                    module_device.kind_name,
                    module_device.parameter_value,
                )

                error_message = self.device_error_message(error_type)
                if error_message is not None:
                    self.error(error_message, module_device.symbol)
                    continue

                self.device_declaration_symbols[internal_device_id] = module_device.symbol
                self.device_module_names[internal_device_id] = module_name
            else:
                self.error("Internal error: unknown module device kind", module_device.symbol)
                return False
                
        # 5. Add all the module's connctions into pending_connections
        for local_input_signal, local_output_signal in module_definition.connections:
            # Here we use map_module_signal_to_instance_signal
            # to convert from a Signal where the main_id just corresponds to the name
            # of the device inside the local module definition, like X1,
            # to a Signal with a main_id of INSTANCENAME->DEVICENAME
            # like H1->X1. 
            # (the main_symbol and port_symbol still point to the symbol in the
            # module definition for error reporting)
            mapped_input_signal = self.map_module_signal_to_instance_signal(local_input_signal, instance_id)
            mapped_output_signal = self.map_module_signal_to_instance_signal(local_output_signal, instance_id)

            # Now, the modules can be inside other modules. 
            # So we must do the same check as in parse_connect, where if the connect destination
            # is a submodule's input/output port, we resolve it to the internal net signal. 

            if(self.is_module_instance_port(mapped_output_signal)):
                if self.module_instance_port_directions[(mapped_output_signal.main_id, mapped_output_signal.port_id)]=="input":
                    # note self.module_instance_port_directions has all instances, even the sub-instances
                    # and the key to the dict is the instance_id, like FA1->HA. 
                    self.error("Module instance's input port cannot be used as a source.", mapped_output_signal.port_symbol)
                    return False
                mapped_output_signal = self.module_instance_ports[(mapped_output_signal.main_id, mapped_output_signal.port_id)]

            if(self.is_module_instance_port(mapped_input_signal)):
                if self.module_instance_port_directions[(mapped_input_signal.main_id, mapped_input_signal.port_id)]=="output":
                    self.error("Module instance's output port cannot be driven from the outside.", mapped_input_signal.port_symbol)
                    return False
                mapped_input_signal = self.module_instance_ports[(mapped_input_signal.main_id, mapped_input_signal.port_id)]

            # For recursive modules we now need this section.
            # This is because now:
            # the mapped_input_signal can be resolved as a net
            # because in the stored module_definition.connections, 
            # LHS could be a submodule port.
            # (so it gets resolved as an internal net, despite
            # not being in the NETS declaration) 

            if self.is_net(mapped_input_signal):
                net_id = mapped_input_signal.main_id
                if(net_id not in self.net_driver_dict):
                    self.net_driver_dict[net_id] = mapped_output_signal
                else:
                    self.error("Net has multiple drivers", mapped_input_signal.main_symbol)
                    return False
            else:
                self.pending_connections.append((mapped_input_signal, mapped_output_signal))

        # 6. Add the module's net drivers to the overall circuit's net drivers dict
        for local_net_id, local_driving_signal in module_definition.net_driver_dict.items():
            internal_net_id = self.make_internal_name_id_from_instance_id(instance_id, local_net_id)
            driving_signal = self.map_module_signal_to_instance_signal(local_driving_signal,instance_id)

            # If the net's driving signal is a port of a sub-module, we must resolve
            # it to the internal net signal in the main circuit. 
            if(self.is_module_instance_port(driving_signal)):
                if self.module_instance_port_directions[(driving_signal.main_id, driving_signal.port_id)]=="input":
                    self.error("Module instance's input port cannot be used as a source.", driving_signal.port_symbol)
                    return False
                driving_signal = self.module_instance_ports[(driving_signal.main_id, driving_signal.port_id)]
            
            self.net_driver_dict[internal_net_id] = driving_signal

        return True
    
    def check_module_instance_inputs_driven(self):
        """Check that every input port of every module instance has a driver, 
        and display a more specific error message if not. 
        """

        # since module instance input ports are represented internally as nets,
        # we use this check to give a scepific error instead of the generic 'Net has no driver'
        # error msg that is created during net flattening.
        no_undriven_inputs = True

        for (instance_id, port_id), internal_signal in self.module_instance_ports.items():
            direction = self.module_instance_port_directions[(instance_id, port_id)]
            if direction != "input":
                continue

            internal_input_net_id = internal_signal.main_id

            if internal_input_net_id not in self.net_driver_dict:
                instance_name = self.names.get_name_string(instance_id)
                port_name = self.names.get_name_string(port_id)

                self.error(
                    "Module instance input port is not driven: "
                    + instance_name + "." + port_name, internal_signal.main_symbol
                )
                no_undriven_inputs = False

        return no_undriven_inputs
    
    
#############################################################################################
# PARSE AND BUILD DEVICES
#############################################################################################

    def parse_device(self):
        """Parse device based on EBNF specification:
         device = device_kind, name_list, ';'.
         Return True if the device statement
         was parsed and consumed, regardless of semantic correctness.
         Return False otherwise"""
        # N.B. we have a separate parse_device_statement to allow 
        # re-use in parse_module_device

        # 1. Parse the device ebnf rule (syntax)

        device_statement_result = self.parse_device_statement()
        if device_statement_result is None:
            return True
        device_kind_symbol, device_kind_result, device_name_list = device_statement_result
        module_or_primitive, device_kind_id, device_parameter = device_kind_result

        if not self.can_build_network():
            return True

        # 2. Actually make the device (and semantic checks)

        if(module_or_primitive == "primitive"):
            for device_name in device_name_list:  # device_name is a symbol
                # check to see if device name conflicts with module name 
                # (we already know it's not a reserved keyword)
                device_name_string = self.names.get_name_string(device_name.id)
                if device_name_string in self.module_definitions:
                    self.error("Device name conflicts with a module name", device_name)
                    continue

                if not self.can_build_network():
                    return True

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
                    continue

                self.device_declaration_symbols[device_name.id] = device_name
                
        elif(module_or_primitive) == "module":
            for device_name in device_name_list:
                if not self.can_build_network():
                    continue
                if not self.instantiate_module(device_name, device_kind_id, device_name.id):
                    continue

        return True

    def parse_devices(self):
        """Parse a list of devices, { device }. 

        return True if parsing ends on the expected next section keyword,
        False if parsing gets lost and can't find the expected structure,
        regardless of semantic corectness. 
        """
        while True:
            if self.is_keyword_name("CONNECT") or self.is_keyword_name("NETS"):
                return True

            if self.symbol.type == self.scanner.EOF or self.is_section_keyword():
                errormsg = "Incorrect structure: DEVICES section should be followed by NETS or CONNECT section."
                errormsg += self.section_typo_hint("NETS")
                errormsg += self.section_typo_hint("CONNECT")
                self.error(errormsg)
                return False

            self.parse_device()

            
#############################################################################################
# PARSE AND BUILD CONNECTIONS
#############################################################################################

    def parse_connect(self):
        """Parse connect based on EBNF specification.
        connect = signal_list, '=', signal, ';'.
        Add all the connections to be made to pending_connections,
        and build net_driver_dict. 
        """

        # 1. Parse the device EBNF rule (syntax)

        connection_statement = self.parse_connection_statement()
        if connection_statement is None:
            return True # parse connection statement guarantees progress
        input_signal_list, output_signal = connection_statement

        # Only proceed beyond syntax checks if we can still build the network,
        # as earlier errors may cause cascading semantic errors
        if not self.can_build_network():
            return True

        # 2. Store the connections to be made, and some net semantic checks
        #     (other semantic checks performed during resolve_and_create_connections)

        if self.net_used_with_port(output_signal):
            self.error("Net cannot have a port", output_signal.port_symbol)
            return True
        
        # If it's a module's output, we need to resolve the signal 
        # to the internal net. 
        # for example, H1.COUT should be converted to the net signal
        # H1->COUT
        
        if(self.is_module_instance_port(output_signal)):
            if self.module_instance_port_directions[(output_signal.main_id, output_signal.port_id)]=="input":
                self.error("Module instance's input port cannot be used as a source.", output_signal.port_symbol)
                return True
            # output_signal.main_id is the ID of the module instance name, output_signal.port_id is the ID of the 
            # module input/output port name
            output_signal = self.module_instance_ports[(output_signal.main_id, output_signal.port_id)]

        elif(not output_signal.is_literal and output_signal.main_id in self.module_instance_ids):
            if output_signal.port_id is None:
                self.error("Output portof module instance not specified", output_signal.main_symbol)
            else:
                self.error("Port does not exist on module instance", output_signal.port_symbol)
            return True

        if(not output_signal.is_literal and not self.is_net(output_signal) and self.devices.get_device(output_signal.main_id) is None):
            errormsg = "Signal name does not exist in this network"
            errormsg += self.signal_name_typo_hint(output_signal.main_id)
            self.error(errormsg, output_signal.main_symbol)
            return True


        for input_signal in input_signal_list:
            if not self.can_build_network():
                break
            # If the LHS is a net, we store its RHS in net_driver_dict
            # (RHS can also be a net, this will be flattened with a call
            # to flatten_net_driver_dict during resolve_and_create_connections)
            if self.net_used_with_port(input_signal):
                self.error("Net cannot have a port", input_signal.port_symbol)
                break

            if(self.is_module_instance_port(input_signal)):
                if self.module_instance_port_directions[(input_signal.main_id, input_signal.port_id)]=="output":
                    self.error("Module instance's output port cannot be driven from the outside.", input_signal.port_symbol)
                    break
                # input_signal.main_id is the ID of the module instance name, input_signal.port_id is the ID of the 
                # module input/output port name
                input_signal = self.module_instance_ports[(input_signal.main_id, input_signal.port_id)]

            elif input_signal.main_id in self.module_instance_ids:
                if input_signal.port_id is None:
                    self.error("Module instance input port not specified", input_signal.main_symbol)
                else:
                    self.error("Port does not exist on module instance", input_signal.port_symbol)
                break
            
            if input_signal.is_literal:
                self.error("Literal (0 or 1) cannot be on LHS of expression", input_signal.main_symbol)
                break

            if (not self.is_net(input_signal) and self.devices.get_device(input_signal.main_id) is None):
                errormsg = "Net/device name does not exist"
                errormsg += self.signal_name_typo_hint(input_signal.main_id)
                self.error(errormsg, input_signal.main_symbol)
                break

            if self.is_net(input_signal):
                net_id = input_signal.main_id
                if(net_id not in self.net_driver_dict):
                    self.net_driver_dict[net_id] = output_signal
                else:
                    self.error("Net has multiple drivers", input_signal.main_symbol)
                    break
                
            # Otherwise if LHS is a regular signal we just add it to the 
            # pending connections list. 
            else:
                self.pending_connections.append((input_signal, output_signal))

        return True
    
    def check_all_device_inputs_driven(self):
        """Check that every input port of every real device has a source.
        Display an error message if some device has an undriven input."""

        if not self.can_build_network():
            return
        # Prevent duplicate reporting of undriven primitive device inputs
        # inside a multiple-times-instantiated module

        # N.B. one might suggest that it is better to do this when parsing the 
        # moduledefinition and not after instantiating it, to avoid this,
        # but in that case we would have to basically rewrite existing checks
        # inside network class about, e.g. what are the names of all the ports
        # of the devices. 

        reported_module_errors = set()

        for device in self.devices.devices_list:
            device_id = device.device_id
            device_name = self.names.get_name_string(device_id)
            for input_id, source in device.inputs.items():
                if source is None:
                    input_name = self.names.get_name_string(input_id)
                    symbol = self.device_declaration_symbols.get(device_id, self.symbol)

                    # If it's inside a module
                    if device_id in self.device_module_names:
                        module_name = self.device_module_names[device_id]
                        # device_name is something like HALFADDER1->X1
                        local_device_name = device_name.split("->")[-1] 

                        error_details = (module_name, local_device_name, input_id)
                        if error_details in reported_module_errors:
                            # We've already issued this same error
                            # (probably for a different instance of this module)
                            continue
                        reported_module_errors.add(error_details)
                        
                        # This assumes that the error is internal to the module, because
                        # when called in resolve_and_create_connections, there had already been a 
                        # check that all module instance inputs are driven
                        self.error("Device input is not driven in module " + module_name + ": "
                            + local_device_name + "." + input_name, symbol)

                    # If it's just a device in the main circuit
                    else:
                        self.error("Device input is not driven: "+ device_name + "." + input_name, symbol)
        return 
    
    def resolve_and_create_connections (self):
        """Resolve all net references in pending_connections, 
        create all the connections in the network, and run semantic checks.
        Only runs if can_build_network i.e. no errors so far."""

        if not self.can_build_network():
            return
        
        if not self.check_module_instance_inputs_driven():
            return

        if not self.flatten_net_driver_dict():
            return
        
        # TODO net unused / not connected to anything checks
        # may want to keep track of the net instantiation symbols for this

        for connection in self.pending_connections:
            if not self.can_build_network():
                break
            input_signal, output_signal = connection

            input_device_id = input_signal.main_id
            input_port_id = input_signal.port_id

            if self.is_net(output_signal):
                net_id = output_signal.main_id

                if net_id not in self.net_driver_dict:
                    self.error("Net has no driver", output_signal.main_symbol)
                    break

                output_signal = self.net_driver_dict[net_id]

            if output_signal.is_literal:
                output_device_id = self.get_or_create_const_switch(output_signal)
                if output_device_id is None:
                    break
                output_port_id = None
            else:
                output_device_id = output_signal.main_id
                output_port_id = output_signal.port_id

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
                    best_error_symbol = input_signal.main_symbol
                elif connection_error_type == self.network.FIRST_PORT_ABSENT:   
                    best_error_symbol = input_signal.port_symbol
                elif connection_error_type == self.network.SECOND_DEVICE_ABSENT:
                    best_error_symbol = output_signal.main_symbol
                elif connection_error_type == self.network.SECOND_PORT_ABSENT:   
                    best_error_symbol = output_signal.port_symbol
                elif connection_error_type == self.network.INPUT_CONNECTED or connection_error_type == self.network.OUTPUT_TO_OUTPUT:
                    if input_signal.port_symbol is None:
                        best_error_symbol = input_signal.main_symbol 
                    else:
                        best_error_symbol = input_signal.port_symbol
                elif connection_error_type == self.network.INPUT_TO_INPUT:
                    if output_signal.port_symbol is None:
                        best_error_symbol = output_signal.main_symbol 
                    else:
                        best_error_symbol = output_signal.port_symbol
                self.error(error_message, best_error_symbol)
                break
        
        self.check_all_device_inputs_driven() # generate an error if not 
        
        return

    def parse_connections(self):
        """Parse connections based on EBNF specification:
         connections = { connect }.
         return True if syntactically successful, False otherwise"""
        while True:
            if self.is_keyword_name("MONITOR"):
                if self.can_build_network():
                    self.resolve_and_create_connections()
                return True

            if self.symbol.type == self.scanner.EOF:
                errormsg = "Unexpected end of file in CONNECT section - expected MONITOR section"
                errormsg += self.section_typo_hint("MONITOR")
                self.error(errormsg)
                return False

            if self.is_section_keyword():
                errormsg = "Incorrect structure - CONNECT section should be followed by MONITOR section"
                errormsg += self.section_typo_hint("MONITOR")
                self.error(errormsg)
                return False             

            if not self.parse_connect():
                return False
                
#############################################################################################
# PARSE AND BUILD MONITORS
#############################################################################################

    def parse_monitors(self):
        """Parse EBNF for monitors section: 
            { signal_list, ";" }
            Return True if parser reaches EOF without getting lost,
            False otherwise. 
        """

        # 1. parse the syntax according to EBNF

        all_monitors_list = []
        while True:

            if self.symbol.type == self.scanner.EOF:
                break

            if self.is_section_keyword():
                self.error("Unexpected section keyword in MONITOR section - MONITOR should be the final section")
                return False
            
            monitor_signals = self.parse_signal_list()
            if monitor_signals is None:
                continue
            
            all_monitors_list.extend(monitor_signals)

            if self.symbol.type != self.scanner.SEMICOLON:
                self.error("Expected semicolon after monitor definition", synchronize=True)
                continue

            self.advance()  # consume the semicolon.

        # 2. create the monitors and detect semantic errors

        if not self.can_build_network():
            return True

        for monitor_signal in all_monitors_list:
            if not self.can_build_network():
                break

            if(monitor_signal.is_literal):
                self.error("Cannot monitor a literal 0 or 1", monitor_signal.main_symbol)
                break
            
            # Store the actual signal requested in the monitors section
            # (so after resolving it we still can point appropriately in
            # error messages)
            requested_signal = monitor_signal

            # The display name for the monitor should be the actual name of the net
            # specified, if the user wants to monitor a net. Thus we store
            # the display name before we resolve the net
            requested_name = self.names.get_name_string(monitor_signal.main_id)
            if monitor_signal.port_symbol is not None:
                requested_name += "." + self.names.get_name_string(monitor_signal.port_id)
            
            # If if's a module, resolve the module instance port into a net name 
            #   (after this, module instance port is treated like an ordinary net)
            if monitor_signal.main_id in self.module_instance_ids:
                if monitor_signal.port_id is None:
                    self.error("Must specify an output port when monitoring a module instance\nor device with multiple output ports", monitor_signal.main_symbol)
                    break
                if not self.is_module_instance_port(monitor_signal):
                    self.error("Port does not exist on module instance", monitor_signal.port_symbol)
                    break
                if self.module_instance_port_directions[(monitor_signal.main_id, monitor_signal.port_id)] == "input":
                    self.error("Cannot monitor a module instance's input port.", monitor_signal.port_symbol)
                    break

                monitor_signal = self.module_instance_ports[(monitor_signal.main_id, monitor_signal.port_id)]       

            # Resolve the net reference into the actual device source 
            if self.is_net(monitor_signal):
                net_id = monitor_signal.main_id

                if net_id not in self.net_driver_dict:
                    self.error("Net has no driver", monitor_signal.main_symbol)
                    break

                monitor_signal = self.net_driver_dict[net_id]

            device_id = monitor_signal.main_id
            port_id = monitor_signal.port_id
            
            error_type = self.monitors.make_monitor(device_id, port_id, requested_name=requested_name)

            error_message = self.monitor_error_message(error_type)
            error_symbol = self.symbol

            if error_message is not None:
                device = self.devices.get_device(device_id)
                if device is None:
                    error_message = "Specified name does not match a device or net"
                    error_message += self.signal_name_typo_hint(requested_signal.main_id)
                    error_symbol = requested_signal.main_symbol
                elif port_id is not None and port_id not in device.outputs:
                    error_message = "Port does not exist or is not an output port"
                    error_symbol = requested_signal.port_symbol
                elif port_id is None and len(device.outputs) > 1:
                    error_message = "Device has multiple output ports - specify which one to monitor"
                    error_symbol = requested_signal.main_symbol

                elif requested_signal.port_symbol is None:
                    error_symbol = requested_signal.main_symbol
                else:
                    error_symbol = requested_signal.port_symbol

                self.error(error_message, error_symbol)
                break
            
        return True 

#############################################################################################
# PARSING: FULL NETWORK (TOP LEVEL FUNCTIONS)
#############################################################################################


    def parse_network(self):
        """Parse the full circuit definition file according to the EBNF specification and 
        create the network, displaying error messages for errors encountered
        Return True if there are no errors, and False otherwise """

        try:

        # self.symbol starts on None, advance it once to get the first symbol
            self.advance()

            while self.is_keyword_name("MODULE"):
                self.parse_module_definition()
                if self.is_keyword_name("MODULE"):
                    continue
                elif self.is_keyword_name("DEVICES"):
                    break
                else:
                    # and next keyword isn't MODULE or DEVICES: fatal error
                    self.fatal_error()
                    return False


            if self.is_keyword_name("DEVICES"):
                self.advance()

                if not self.parse_devices():
                    self.fatal_error()
                    return False
            else:
                errormsg = "Expected DEVICES section or new MODULE definition."
                errormsg += self.section_typo_hint("DEVICES")
                errormsg += self.section_typo_hint("MODULE")
                self.error(errormsg)
                self.fatal_error()
                return False
            
            if self.is_keyword_name("NETS"):
                self.advance()

                if not self.parse_nets():
                    self.fatal_error()
                    return False

            if self.is_keyword_name("CONNECT"):
                self.advance()

                if not self.parse_connections():
                    self.fatal_error()
                    return False
            else:
                errormsg = "CONNECT section not found after DEVICES section"
                errormsg += self.section_typo_hint("CONNECT")
                self.error(errormsg)
                self.fatal_error()
                return False

            if self.is_keyword_name("MONITOR"):
                self.advance()

                if not self.parse_monitors():
                    self.fatal_error()
                    return False
            else:
                errormsg = "MONITOR section not found after CONNECT section"
                errormsg += self.section_typo_hint("MONITOR")
                self.error(errormsg, synchronize=True)
                self.fatal_error()
                return False

            if self.symbol.type != self.scanner.EOF:
                self.error("Expected end of file - MONITOR section should be the final section", synchronize=True)
                self.fatal_error()
                return False
            


            if self.error_count == 0:
                print("---------------------------------------------------------------")
                print("SUCCESS: Parsing finished with no error\n")
                return True
            else:
                print("---------------------------------------------------------------")
                if(self.error_count > MAX_ERROR_MSGS):
                    print("And "+str(self.error_count-MAX_ERROR_MSGS)+" more error(s)...")
                    print("---------------------------------------------------------------")
                print("*** UNSUCCESSFUL: " + str(self.error_count) + " error(s) found during parsing. ***\n")
                print("Network not built. Simulation will not start until the definition file is fixed.\n")

                return False
        
        except Exception:
            # FALLBACK ERROR MESSAGE - This should hopefully not ever be seen by the user! 
            print("---------------------------------------------------------------")
            try:
                self.error_count += 1
                self.error("An unexpected error occurred - please check the definition file")
                print("*** ERROR: Parsing stopped with " + str(self.error_count) + " error(s) ***\n")
            except Exception:
                print("*** Error in definition file - parsing not completed ***")
                pass
            print("Simulation will not start until the definition file is fixed.")
            return False

