"""Parse the definition file and build the logic network.

Used in the Logic Simulator project to analyse the syntactic and semantic
correctness of the symbols received from the scanner and then builds the
logic network.

Classes
-------
Parser - parses the definition file and builds the logic network.
"""


class Parser:
    """Parse a definition file and build the logic network.

    The parser validates syntax and semantics for the scanner symbols and then
    constructs the corresponding devices, connections and monitors for the
    Logic Simulator.
    """

    def __init__(self, names, devices, network, monitors, scanner):
        """Initialise parser state with the required managers and scanner.

        Parameters
        ----------
        names : Names
            Symbol table for keyword and device name lookup.
        devices : Devices
            Device manager used to instantiate devices.
        network : Network
            Network manager used to create connections.
        monitors : Monitors
            Monitors manager used to register signal monitors.
        scanner : Scanner
            Scanner used to retrieve symbols from the definition file.
        """
        self.names = names
        self.devices = devices
        self.network = network
        self.monitors = monitors
        self.scanner = scanner

        self.error_count = 0
        self.symbol = None

        [self.k_devices, self.k_connect, self.k_monitor] = self.names.lookup(
            ["DEVICES", "CONNECT", "MONITOR"]
        )
        [self.k_switch] = self.names.lookup(["SWITCH"])

        self.param_device_ids = set(
            self.names.lookup(["AND", "NAND", "OR", "NOR", "CLOCK", "SWITCH"])
        )
        self.fixed_device_ids = set(self.names.lookup(["DTYPE", "XOR"]))
        self.device_kind_ids = self.param_device_ids | self.fixed_device_ids

    def next_sym(self):
        """Advance to the next symbol from the scanner."""
        self.symbol = self.scanner.get_symbol()

    def display_error(self, message, stopping_types):
        """Displays a syntax error and synchronises the scanner to recover."""
        self.error_count += 1
        print(f"\nSyntax Error: {message}")
        if self.symbol:
            self.scanner.print_error_line(self.symbol.line_num, self.symbol.line_pos)
        self.synchronise(stopping_types)

    def synchronise(self, stopping_types):
        """Advances the scanner until a stopping symbol or EOF is reached."""
        while (
            self.symbol.type not in stopping_types
            and self.symbol.type != self.scanner.EOF
        ):
            self.next_sym()

    def display_semantic_error(self, message, symbol):
        """Displays a specific semantic error pointing to an exact Symbol."""
        self.error_count += 1
        print(f"\nSemantic Error: {message}")
        if symbol:
            self.scanner.print_error_line(symbol.line_num, symbol.line_pos)

    def get_device_error_msg(self, error_type):
        """Map a device error code to a human-readable message.

        Parameters
        ----------
        error_type : int
            Error code returned by the device manager.

        Returns
        -------
        str
            Description of the device error.
        """
        if error_type == self.devices.INVALID_QUALIFIER:
            return "Invalid parameter for this device kind."
        if error_type == self.devices.NO_QUALIFIER:
            return "Missing numerical parameter for parameterised device."
        if error_type == self.devices.BAD_DEVICE:
            return "Unknown device kind."
        if error_type == self.devices.QUALIFIER_PRESENT:
            return "This fixed device kind should not have a parameter."
        if error_type == self.devices.DEVICE_PRESENT:
            return "Device name has already been defined."
        return f"Unknown device error (Code {error_type})."

    def get_monitor_error_msg(self, error_type):
        """Map a monitor error code to a human-readable message.

        Parameters
        ----------
        error_type : int
            Error code returned by the monitors manager.

        Returns
        -------
        str
            Description of the monitor error.
        """
        if error_type == self.monitors.NOT_OUTPUT:
            return "Cannot monitor an input or non-existent port."
        if error_type == self.monitors.MONITOR_PRESENT:
            return "Signal is already being monitored."
        if error_type == self.monitors.DEVICE_ABSENT:
            return "Device does not exist."
        return f"Unknown monitor error (Code {error_type})."

    def resolve_network_error(
        self, err_code, dest_dev, dest_port, src_dev, src_port, src_lit
    ):
        """Resolves precision pointers for Kevin's split network errors."""
        msg = "Unknown connection error."
        target_sym = dest_port or dest_dev

        if err_code == self.network.FIRST_DEVICE_ABSENT:
            msg = "Destination device does not exist."
            target_sym = dest_dev
        elif err_code == self.network.FIRST_PORT_ABSENT:
            msg = "Destination port does not exist on this device."
            target_sym = dest_port or dest_dev
        elif err_code == self.network.SECOND_DEVICE_ABSENT:
            msg = "Source device does not exist."
            target_sym = src_dev or src_lit
        elif err_code == self.network.SECOND_PORT_ABSENT:
            msg = "Source port does not exist on this device."
            target_sym = src_port or src_dev
        elif err_code == self.network.INPUT_CONNECTED:
            msg = "Destination input is already connected to another source."
            target_sym = dest_port or dest_dev
        elif err_code == self.network.INPUT_TO_INPUT:
            msg = "Cannot connect an input to another input. Source must be an output."
            target_sym = src_port or src_dev
        elif err_code == self.network.OUTPUT_TO_OUTPUT:
            msg = (
                "Cannot connect an output to another output. "
                "Destination must be an input."
            )
            target_sym = dest_port or dest_dev

        return msg, target_sym

    def parse_network(self):
        """Parse the complete network definition from the file.

        The parser expects the file to contain DEVICES, CONNECT and MONITOR
        blocks in that order. If the definition is syntactically and
        semantically valid, the method returns True.
        """
        self.next_sym()

        if (
            self.symbol.type == self.scanner.KEYWORD
            and self.symbol.id == self.k_devices
        ):
            self.next_sym()
            while self.symbol.type != self.scanner.EOF and not (
                self.symbol.type == self.scanner.KEYWORD
                and self.symbol.id in (self.k_connect, self.k_monitor)
            ):
                self.parse_device()
        else:
            self.display_error(
                "Expected 'DEVICES' block at the start of the file.",
                (self.scanner.KEYWORD, self.scanner.EOF),
            )

        if (
            self.symbol.type == self.scanner.KEYWORD
            and self.symbol.id == self.k_connect
        ):
            self.next_sym()
            while self.symbol.type != self.scanner.EOF and not (
                self.symbol.type == self.scanner.KEYWORD
                and self.symbol.id == self.k_monitor
            ):
                self.parse_connect()
        else:
            self.display_error(
                "Expected 'CONNECT' block following devices.",
                (self.scanner.KEYWORD, self.scanner.EOF),
            )

        if (
            self.symbol.type == self.scanner.KEYWORD
            and self.symbol.id == self.k_monitor
        ):
            self.next_sym()
            while self.symbol.type not in (self.scanner.EOF, self.scanner.KEYWORD):
                self.parse_monitor()
        else:
            self.display_error(
                "Expected 'MONITOR' block following connections.", (self.scanner.EOF,)
            )

        if self.symbol.type != self.scanner.EOF:
            self.display_error(
                "Expected end of file. Found unexpected tokens.", (self.scanner.EOF,)
            )

        if self.error_count == 0:
            if not self.network.check_network():
                self.display_semantic_error(
                    "Circuit is incomplete: Not all inputs are connected.", self.symbol
                )
                return False

        return self.error_count == 0

    def parse_device(self):
        """Parse a device declaration and instantiate devices if valid.

        The method checks the device kind, parses the device names and then
        creates each device if there are no syntax or semantic errors.
        """
        stopping_types = (
            self.scanner.SEMICOLON,
            self.scanner.KEYWORD,
            self.scanner.EOF,
        )

        device_kind_id, param_sym = self.parse_device_kind(stopping_types)

        if device_kind_id is None:
            self.synchronise(stopping_types)
            name_symbols = None
        else:
            name_symbols = self.parse_name_list(stopping_types)
            if name_symbols is None:
                self.synchronise(stopping_types)

        if self.symbol.type == self.scanner.SEMICOLON:
            self.next_sym()

            if self.error_count == 0 and device_kind_id is not None and name_symbols:
                for name_sym in name_symbols:
                    param_val = param_sym.id if param_sym else None
                    err = self.devices.make_device(
                        name_sym.id, device_kind_id, param_val
                    )
                    if err != self.devices.NO_ERROR:
                        msg = self.get_device_error_msg(err)
                        self.display_semantic_error(msg, name_sym)
        else:
            self.display_error(
                "Missing semicolon: A device declaration must end with a ';'.",
                (self.scanner.KEYWORD, self.scanner.NAME, self.scanner.EOF),
            )

    def parse_device_kind(self, stopping_types):
        """Parse a device kind token and optional parameter.

        Parameters
        ----------
        stopping_types : tuple
            Symbol types that stop parsing at this point.

        Returns
        -------
        tuple
            A tuple containing the device kind ID and the parameter symbol,
            or (None, None) if parsing failed.
        """
        kind_id = self.symbol.id
        param_sym = None

        if (
            self.symbol.type == self.scanner.KEYWORD
            and kind_id in self.param_device_ids
        ):
            self.next_sym()
            if self.symbol.type == self.scanner.L_BRACKET:
                self.next_sym()
                if self.symbol.type == self.scanner.NUMBER:
                    param_sym = self.symbol
                    self.next_sym()
                    if self.symbol.type == self.scanner.R_BRACKET:
                        self.next_sym()
                    else:
                        self.display_error(
                            "Missing closing bracket ')'.", stopping_types
                        )
                        return None, None
                else:
                    self.display_error(
                        "Expected a numerical parameter.", stopping_types
                    )
                    return None, None
            else:
                self.display_error("Missing parameter brackets '('.", stopping_types)
                return None, None

        elif (
            self.symbol.type == self.scanner.KEYWORD
            and kind_id in self.fixed_device_ids
        ):
            self.next_sym()

        else:
            self.display_error("Unknown device kind.", stopping_types)
            return None, None

        return kind_id, param_sym

    def parse_name_list(self, stopping_types):
        """Parse a comma-separated list of device names.

        Parameters
        ----------
        stopping_types : tuple
            Symbol types that terminate the name list.

        Returns
        -------
        list
            A list of name symbols, or None if parsing failed.
        """
        names = []

        if self.symbol.type == self.scanner.NAME:
            names.append(self.symbol)
            self.next_sym()

            while (
                self.symbol.type == self.scanner.COMMA
                and self.symbol.type != self.scanner.EOF
            ):
                self.next_sym()
                if self.symbol.type == self.scanner.NAME:
                    names.append(self.symbol)
                    self.next_sym()
                elif self.symbol.type == self.scanner.KEYWORD:
                    kw_str = self.names.get_name_string(self.symbol.id)
                    self.display_error(
                        f"Cannot use reserved keyword '{kw_str}' as a device name.",
                        stopping_types,
                    )
                    return None
                else:
                    self.display_error(
                        "Trailing comma or missing name in list.", stopping_types
                    )
                    return None
        elif self.symbol.type == self.scanner.KEYWORD:
            kw_str = self.names.get_name_string(self.symbol.id)
            self.display_error(
                f"Cannot use reserved keyword '{kw_str}' as a device name.",
                stopping_types,
            )
            return None
        else:
            self.display_error("Expected at least one device name.", stopping_types)
            return None

        return names

    def get_hidden_literal_id(self, literal_val):
        """Generates or retrieves the ID for a hidden switch representing a literal."""
        lit_name = f"__LITERAL_{literal_val}__"
        [lit_id] = self.names.lookup([lit_name])

        # If the switch doesn't exist, build it silently
        if self.devices.get_device(lit_id) is None:
            self.devices.make_device(lit_id, self.k_switch, literal_val)

        return lit_id

    def parse_connect(self):
        """Parse a connection statement and build network links.

        The method parses the destination signal list, the source expression
        and then creates connections if the syntax and semantics are valid.
        """
        stopping_types = (
            self.scanner.SEMICOLON,
            self.scanner.KEYWORD,
            self.scanner.EOF,
        )
        destinations = self.parse_signal_list((self.scanner.EQUALS, *stopping_types))

        if destinations is None:
            self.synchronise(stopping_types)
            source_dev, source_port, lit_sym = None, None, None
        else:
            if self.symbol.type == self.scanner.EQUALS:
                self.next_sym()
                source_dev, source_port, lit_sym = self.parse_source(stopping_types)
                if source_dev is None and source_port is None and lit_sym is None:
                    self.synchronise(stopping_types)
            else:
                self.display_error(
                    "Missing equals sign '=' in connection.", stopping_types
                )
                source_dev, source_port, lit_sym = None, None, None

        if self.symbol.type == self.scanner.SEMICOLON:
            self.next_sym()

            if (
                self.error_count == 0
                and destinations
                and (source_dev or source_port or lit_sym)
            ):
                s_dev_id, s_port_id = None, None
                if lit_sym is not None:
                    s_dev_id = self.get_hidden_literal_id(lit_sym.id)
                else:
                    s_dev_id = source_dev.id if source_dev else None
                    s_port_id = source_port.id if source_port else None

                for dest_dev, dest_port in destinations:
                    d_dev_id = dest_dev.id
                    d_port_id = dest_port.id if dest_port else None

                    err = self.network.make_connection(
                        d_dev_id, d_port_id, s_dev_id, s_port_id
                    )

                    if err != self.network.NO_ERROR:
                        msg, tgt_sym = self.resolve_network_error(
                            err, dest_dev, dest_port, source_dev, source_port, lit_sym
                        )
                        self.display_semantic_error(msg, tgt_sym)
        else:
            self.display_error(
                "Missing semicolon ';' at the end of the connection.",
                (self.scanner.KEYWORD, self.scanner.NAME, self.scanner.EOF),
            )

    def parse_monitor(self):
        """Parse a monitor statement and configure monitors.

        The method parses a list of signals to monitor and registers each with
        the monitors manager if there are no syntax or semantic errors.
        """
        stopping_types = (
            self.scanner.SEMICOLON,
            self.scanner.KEYWORD,
            self.scanner.EOF,
        )
        signals = self.parse_signal_list(stopping_types)

        if signals is None:
            self.synchronise(stopping_types)

        if self.symbol.type == self.scanner.SEMICOLON:
            self.next_sym()

            if self.error_count == 0 and signals:
                for dev_sym, port_sym in signals:
                    dev_id = dev_sym.id
                    port_id = port_sym.id if port_sym else None

                    err = self.monitors.make_monitor(dev_id, port_id)
                    if err != self.monitors.NO_ERROR:
                        msg = self.get_monitor_error_msg(err)
                        self.display_semantic_error(
                            msg, port_sym if port_sym else dev_sym
                        )
                    else:
                        display_name = self.names.get_name_string(dev_id)
                        if port_sym:
                            display_name += f".{self.names.get_name_string(port_id)}"
                        self.monitors.set_monitor_display_name(
                            dev_id, port_id, display_name
                        )
        else:
            self.display_error(
                "Missing semicolon ';' at the end of the monitor statement.",
                (self.scanner.KEYWORD, self.scanner.NAME, self.scanner.EOF),
            )

    def parse_signal_list(self, stopping_types):
        """Parse a list of signals separated by commas.

        Parameters
        ----------
        stopping_types : tuple
            Symbol types that terminate the signal list.

        Returns
        -------
        list
            A list of (device symbol, port symbol) tuples, or None if parsing failed.
        """
        signals = []

        dev_sym, port_sym = self.parse_signal((self.scanner.COMMA, *stopping_types))
        if dev_sym is None and port_sym is None:
            return None

        signals.append((dev_sym, port_sym))

        while (
            self.symbol.type == self.scanner.COMMA
            and self.symbol.type != self.scanner.EOF
        ):
            self.next_sym()
            dev_sym, port_sym = self.parse_signal((self.scanner.COMMA, *stopping_types))
            if dev_sym is not None or port_sym is not None:
                signals.append((dev_sym, port_sym))
            else:
                self.display_error(
                    "Trailing comma or invalid signal in list.", stopping_types
                )
                return None

        return signals

    def parse_signal(self, stopping_types):
        """Parse a device signal reference, optionally including a port.

        Parameters
        ----------
        stopping_types : tuple
            Symbol types that terminate the signal reference.

        Returns
        -------
        tuple
            A tuple of (device symbol, port symbol), or (None, None) if parsing failed.
        """
        dev_sym, port_sym = None, None

        if self.symbol.type == self.scanner.NAME:
            dev_sym = self.symbol
            self.next_sym()
            if self.symbol.type == self.scanner.DOT:
                self.next_sym()
                if self.symbol.type == self.scanner.NAME:
                    port_sym = self.symbol
                    self.next_sym()
                elif self.symbol.type == self.scanner.KEYWORD:
                    kw_str = self.names.get_name_string(self.symbol.id)
                    self.display_error(
                        f"Cannot use reserved keyword '{kw_str}' as a port name.",
                        stopping_types,
                    )
                    return None, None
                else:
                    self.display_error(
                        "Expected a port name after '.' notation.", stopping_types
                    )
                    return None, None
        elif self.symbol.type == self.scanner.KEYWORD:
            kw_str = self.names.get_name_string(self.symbol.id)
            self.display_error(
                f"Cannot use reserved keyword '{kw_str}' as a signal name.",
                stopping_types,
            )
            return None, None
        else:
            self.display_error("Expected a valid signal name.", stopping_types)
            return None, None

        return dev_sym, port_sym

    def parse_source(self, stopping_types):
        """Parse a source expression for a connection statement.

        The source may be a literal 0 or 1, or a signal reference comprising a
        device name and optional port.

        Parameters
        ----------
        stopping_types : tuple
            Symbol types that terminate the source expression.

        Returns
        -------
        tuple
            A tuple of (device symbol, port symbol, literal symbol).
        """
        if self.symbol.type == self.scanner.NUMBER:
            val_sym = self.symbol
            self.next_sym()
            if val_sym.id in (0, 1):
                return None, None, val_sym
            else:
                self.display_error(
                    "Invalid literal: The only valid logic literals are 0 and 1.",
                    stopping_types,
                )
                return None, None, None
        else:
            dev_sym, port_sym = self.parse_signal(stopping_types)
            return dev_sym, port_sym, None
