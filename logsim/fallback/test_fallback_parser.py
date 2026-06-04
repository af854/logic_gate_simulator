from unittest.mock import MagicMock

import pytest
from fallback_parser import Parser

# --- Helper Classes and Fixtures ---


class MockSymbol:
    """A simple struct to simulate the Symbol objects returned by the scanner."""

    def __init__(self, type, id=None):
        self.type = type
        self.id = id
        self.line_num = 1
        self.line_pos = 1


@pytest.fixture
def parser_setup():
    """Sets up a Parser instance with mocked dependencies and predefined tokens."""
    names = MagicMock()
    devices = MagicMock()
    network = MagicMock()
    monitors = MagicMock()
    scanner = MagicMock()

    # Define common Scanner token constants
    scanner.EOF = "EOF"
    scanner.KEYWORD = "KEYWORD"
    scanner.NAME = "NAME"
    scanner.NUMBER = "NUMBER"
    scanner.SEMICOLON = "SEMICOLON"
    scanner.L_BRACKET = "L_BRACKET"
    scanner.R_BRACKET = "R_BRACKET"
    scanner.COMMA = "COMMA"
    scanner.DOT = "DOT"
    scanner.EQUALS = "EQUALS"

    # Mock the name table lookups to return specific IDs during Parser __init__
    def lookup_side_effect(names_list):
        if names_list == ["DEVICES", "CONNECT", "MONITOR"]:
            return [1, 2, 3]
        if names_list == ["SWITCH"]:
            return [4]
        if names_list == ["AND", "NAND", "OR", "NOR", "CLOCK", "SWITCH"]:
            return [10, 11, 12, 13, 14, 4]
        if names_list == ["DTYPE", "XOR"]:
            return [20, 21]
        # For arbitrary literals or unhandled lookups, return unique dummy IDs
        return [hash(n) % 1000 + 100 for n in names_list]

    names.lookup.side_effect = lookup_side_effect
    names.get_name_string.return_value = "MOCK_NAME"

    # Initialize parser
    parser = Parser(names, devices, network, monitors, scanner)

    return parser, names, devices, network, monitors, scanner


# --- Tests for Error Message Translation ---


@pytest.mark.parametrize(
    "error_code, expected_msg",
    [
        (1, "Invalid parameter for this device kind."),  # INVALID_QUALIFIER = 1
        (
            2,
            "Missing numerical parameter for parameterised device.",
        ),  # NO_QUALIFIER = 2
        (3, "Unknown device kind."),  # BAD_DEVICE = 3
        (
            4,
            "This fixed device kind should not have a parameter.",
        ),  # QUALIFIER_PRESENT = 4
        (5, "Device name has already been defined."),  # DEVICE_PRESENT = 5
        (99, "Unknown device error (Code 99)."),
    ],
)
def test_get_device_error_msg(parser_setup, error_code, expected_msg):
    parser, _, devices, _, _, _ = parser_setup

    # Mocking device error constants
    devices.INVALID_QUALIFIER = 1
    devices.NO_QUALIFIER = 2
    devices.BAD_DEVICE = 3
    devices.QUALIFIER_PRESENT = 4
    devices.DEVICE_PRESENT = 5

    assert parser.get_device_error_msg(error_code) == expected_msg


@pytest.mark.parametrize(
    "error_code, expected_msg",
    [
        (1, "Cannot monitor an input or non-existent port."),  # NOT_OUTPUT = 1
        (2, "Signal is already being monitored."),  # MONITOR_PRESENT = 2
        (3, "Device does not exist."),  # DEVICE_ABSENT = 3
        (99, "Unknown monitor error (Code 99)."),
    ],
)
def test_get_monitor_error_msg(parser_setup, error_code, expected_msg):
    parser, _, _, _, monitors, _ = parser_setup

    monitors.NOT_OUTPUT = 1
    monitors.MONITOR_PRESENT = 2
    monitors.DEVICE_ABSENT = 3

    assert parser.get_monitor_error_msg(error_code) == expected_msg


# --- Tests for Unit Parsing Methods ---


def test_parse_name_list_valid(parser_setup):
    """Test parsing a valid comma-separated name list: NAME1, NAME2"""
    parser, _, _, _, _, scanner = parser_setup

    # Simulate token sequence: NAME(50), COMMA, NAME(51), EOF
    scanner.get_symbol.side_effect = [
        MockSymbol(scanner.NAME, 50),
        MockSymbol(scanner.COMMA),
        MockSymbol(scanner.NAME, 51),
        MockSymbol(scanner.EOF),
    ]

    parser.next_sym()  # Load first symbol
    names = parser.parse_name_list((scanner.EOF,))

    assert len(names) == 2
    assert names[0].id == 50
    assert names[1].id == 51
    assert parser.error_count == 0


def test_parse_name_list_trailing_comma(parser_setup):
    """Test parsing a name list with an invalid trailing comma."""
    parser, _, _, _, _, scanner = parser_setup

    scanner.get_symbol.side_effect = [
        MockSymbol(scanner.NAME, 50),
        MockSymbol(scanner.COMMA),
        MockSymbol(scanner.EOF),  # Trailing comma
    ]

    parser.next_sym()
    names = parser.parse_name_list((scanner.EOF,))

    assert names is None
    assert parser.error_count == 1


def test_parse_device_kind_parameterised(parser_setup):
    """Test parsing a parameterised device like AND(2)"""
    parser, _, _, _, _, scanner = parser_setup

    scanner.get_symbol.side_effect = [
        MockSymbol(scanner.KEYWORD, 10),  # 'AND' ID
        MockSymbol(scanner.L_BRACKET),
        MockSymbol(scanner.NUMBER, 2),
        MockSymbol(scanner.R_BRACKET),
        MockSymbol(scanner.EOF),
    ]

    parser.next_sym()
    kind_id, param_sym = parser.parse_device_kind((scanner.EOF,))

    assert kind_id == 10
    assert param_sym.id == 2
    assert parser.error_count == 0


def test_parse_device_kind_fixed(parser_setup):
    """Test parsing a fixed device like DTYPE"""
    parser, _, _, _, _, scanner = parser_setup

    scanner.get_symbol.side_effect = [
        MockSymbol(scanner.KEYWORD, 20),  # 'DTYPE' ID
        MockSymbol(scanner.EOF),
    ]

    parser.next_sym()
    kind_id, param_sym = parser.parse_device_kind((scanner.EOF,))

    assert kind_id == 20
    assert param_sym is None
    assert parser.error_count == 0


def test_parse_signal_with_port(parser_setup):
    """Test parsing a signal with dot notation: DEVICE.PORT"""
    parser, _, _, _, _, scanner = parser_setup

    scanner.get_symbol.side_effect = [
        MockSymbol(scanner.NAME, 50),
        MockSymbol(scanner.DOT),
        MockSymbol(scanner.NAME, 51),
        MockSymbol(scanner.EOF),
    ]

    parser.next_sym()
    dev_sym, port_sym = parser.parse_signal((scanner.EOF,))

    assert dev_sym.id == 50
    assert port_sym.id == 51
    assert parser.error_count == 0


def test_parse_source_literal(parser_setup):
    """Test parsing a valid literal source (0 or 1)."""
    parser, _, _, _, _, scanner = parser_setup

    scanner.get_symbol.side_effect = [
        MockSymbol(scanner.NUMBER, 1),
        MockSymbol(scanner.EOF),
    ]

    parser.next_sym()
    dev_sym, port_sym, lit_sym = parser.parse_source((scanner.EOF,))

    assert dev_sym is None
    assert port_sym is None
    assert lit_sym.id == 1
    assert parser.error_count == 0


def test_get_hidden_literal_id(parser_setup):
    """Test that a hidden switch is generated properly for a literal."""
    parser, names, devices, _, _, _ = parser_setup

    # Pretend device isn't in devices manager yet
    devices.get_device.return_value = None

    lit_id = parser.get_hidden_literal_id(0)

    # Must have called make_device to generate the hidden literal switch
    devices.make_device.assert_called_once_with(lit_id, parser.k_switch, 0)


# --- Tests for Full Blocks ---


def test_parse_network_valid_flow(parser_setup):
    """Test parsing a complete, syntactically correct minimum network."""
    parser, _, _, network, _, scanner = parser_setup

    network.check_network.return_value = True  # Circuit complete

    # Sequence: DEVICES ; CONNECT ; MONITOR ; EOF
    scanner.get_symbol.side_effect = [
        MockSymbol(scanner.KEYWORD, 1),  # DEVICES
        # (Assuming empty device block for pure structural test)
        MockSymbol(scanner.KEYWORD, 2),  # CONNECT
        MockSymbol(scanner.KEYWORD, 3),  # MONITOR
        MockSymbol(scanner.EOF),
    ]

    is_valid = parser.parse_network()

    assert is_valid is True
    assert parser.error_count == 0


def test_parse_network_missing_devices_block(parser_setup):
    """Test error generation when the DEVICES block is missing."""
    parser, _, _, _, _, scanner = parser_setup

    # Provide CONNECT directly without DEVICES
    scanner.get_symbol.side_effect = [
        MockSymbol(scanner.KEYWORD, 2),  # CONNECT
        MockSymbol(scanner.EOF),
    ]

    is_valid = parser.parse_network()

    assert is_valid is False
    assert parser.error_count > 0


def test_parse_network_incomplete_circuit(parser_setup):
    """Test semantic error triggered when the network check fails at the end."""
    parser, _, _, network, _, scanner = parser_setup

    # Simulate valid syntax structure
    scanner.get_symbol.side_effect = [
        MockSymbol(scanner.KEYWORD, 1),  # DEVICES
        MockSymbol(scanner.KEYWORD, 2),  # CONNECT
        MockSymbol(scanner.KEYWORD, 3),  # MONITOR
        MockSymbol(scanner.EOF),
    ]

    # Network checking fails
    network.check_network.return_value = False

    is_valid = parser.parse_network()

    assert is_valid is False
    assert parser.error_count == 1  # Caught the semantic error
