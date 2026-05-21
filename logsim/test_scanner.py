"""Test the scanner module.

Used in the Logic Simulator project to comprehensively test the Scanner
and Symbol classes using pytest.

Tests cover initialization, file handling, regex-based lexical tokenization,
line coordinate tracking via bisection, and error reporting padding.
"""

import pytest
from names import Names
from scanner import Scanner, Symbol


@pytest.fixture
def new_names():
    """Return a fresh instance of the Names class for each test."""
    return Names()


@pytest.fixture
def create_definition_file(tmp_path):
    """Return a factory function to create temporary circuit definition files.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Built-in pytest fixture for creating temporary directories.

    Returns
    -------
    function
        A function that writes a string to a temporary file and returns its path.
    """

    def _create_file(content):
        file_path = tmp_path / "test_def.txt"
        file_path.write_text(content, encoding="utf-8")
        return str(file_path)

    return _create_file


def test_symbol_initialization():
    """Test that Symbol objects correctly assign initialization parameters."""
    sym = Symbol(symbol_type=8, symbol_id=12, line_num=2, line_pos=5)
    assert sym.type == 8
    assert sym.id == 12
    assert sym.line_num == 2
    assert sym.line_pos == 5


def test_scanner_file_not_found(new_names, capsys):
    """Test that Scanner exits cleanly with an error on missing files."""
    with pytest.raises(SystemExit) as exc_info:
        Scanner("non_existent_file.txt", new_names)

    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "Error opening file" in captured.out
    assert "non_existent_file.txt" in captured.out


@pytest.mark.parametrize(
    "char, expected_attr",
    [
        (",", "COMMA"),
        (";", "SEMICOLON"),
        ("=", "EQUALS"),
        (".", "DOT"),
        ("(", "L_BRACKET"),
        (")", "R_BRACKET"),
    ],
)
def test_scanner_punctuation(new_names, create_definition_file, char, expected_attr):
    """Test that all valid EBNF punctuation characters are typed correctly."""
    file_path = create_definition_file(char)
    scanner = Scanner(file_path, new_names)

    symbol = scanner.get_symbol()
    expected_type = getattr(scanner, expected_attr)

    assert symbol.type == expected_type
    assert symbol.id is None


def test_scanner_numbers(new_names, create_definition_file):
    """Test that numeric strings map to NUMBER types with integer IDs."""
    file_path = create_definition_file("0 42 09")
    scanner = Scanner(file_path, new_names)

    assert scanner.get_symbol().id == 0
    assert scanner.get_symbol().id == 42
    assert scanner.get_symbol().id == 9


@pytest.mark.parametrize(
    "keyword",
    [
        "DEVICES",
        "NETS",
        "CONNECT",
        "MONITOR",
        "AND",
        "NAND",
        "OR",
        "NOR",
        "CLOCK",
        "SWITCH",
        "DTYPE",
        "XOR",
        "MODULE",
        "INPUTS",
        "OUTPUTS",
        "ENDMODULE",
    ],
)
def test_scanner_keywords(new_names, create_definition_file, keyword):
    """Test that valid reserved logic gates/commands trigger KEYWORD type."""
    file_path = create_definition_file(keyword)
    scanner = Scanner(file_path, new_names)

    symbol = scanner.get_symbol()
    assert symbol.type == scanner.KEYWORD
    assert symbol.id == scanner.keyword_map[keyword]


def test_scanner_names(new_names, create_definition_file):
    """Test that non-keyword alphanumeric identifiers parse as NAME types."""
    # Tests standard names and names with the newly supported underscore
    file_path = create_definition_file("Gate_1 inputA")
    scanner = Scanner(file_path, new_names)

    sym1 = scanner.get_symbol()
    assert sym1.type == scanner.NAME
    assert sym1.id == new_names.query("Gate_1")

    sym2 = scanner.get_symbol()
    assert sym2.type == scanner.NAME
    assert sym2.id == new_names.query("inputA")


def test_scanner_skips(new_names, create_definition_file):
    """Test that whitespace and EBNF single/multi-line comments are ignored."""
    content = " \n \t (* comment *) (* multiline\n comment *) 42"
    file_path = create_definition_file(content)
    scanner = Scanner(file_path, new_names)

    sym = scanner.get_symbol()
    assert sym.type == scanner.NUMBER
    assert sym.id == 42


def test_scanner_unknown_characters(new_names, create_definition_file):
    """Test that illegal characters are gracefully skipped per regex fallback."""
    file_path = create_definition_file("@ # ! 42")
    scanner = Scanner(file_path, new_names)

    # Should silently drop @, #, ! and return the first valid token
    sym = scanner.get_symbol()
    assert sym.type == scanner.NUMBER
    assert sym.id == 42


def test_scanner_eof(new_names, create_definition_file):
    """Test that the EOF symbol is correctly generated at file termination."""
    file_path = create_definition_file("A")
    scanner = Scanner(file_path, new_names)

    _ = scanner.get_symbol()  # Consume "A"
    sym = scanner.get_symbol()  # Next should be EOF
    assert sym.type == scanner.EOF
    assert sym.line_num == 0
    assert sym.line_pos == 1


def test_scanner_line_tracking(new_names, create_definition_file):
    """Test that line numbers and column positions are rigorously tracked."""
    content = "A = 12;\n(* skip \n me *)\nB"
    file_path = create_definition_file(content)
    scanner = Scanner(file_path, new_names)

    sym_a = scanner.get_symbol()
    assert sym_a.line_num == 0
    assert sym_a.line_pos == 0

    sym_eq = scanner.get_symbol()
    assert sym_eq.line_num == 0
    assert sym_eq.line_pos == 2

    sym_num = scanner.get_symbol()
    assert sym_num.line_num == 0
    assert sym_num.line_pos == 4

    sym_semi = scanner.get_symbol()
    assert sym_semi.line_num == 0
    assert sym_semi.line_pos == 6

    # Line index 3 (the 4th line physically): "B"
    sym_b = scanner.get_symbol()
    assert sym_b.line_num == 3
    assert sym_b.line_pos == 0


def test_scanner_print_error_line(new_names, create_definition_file, capsys):
    """Test the visual layout and dynamic padding (including tabs) of errors."""
    content = "\tCONNECT A = B.I1;"
    file_path = create_definition_file(content)
    scanner = Scanner(file_path, new_names)

    # Trigger an error pointer on the '=' sign (index 11 due to leading tab)
    scanner.print_error_line(0, 11)

    captured = capsys.readouterr()
    printed_lines = captured.out.split("\n")

    assert printed_lines[0] == content
    # The padding must strictly preserve the tab character, followed by spaces
    expected_marker = "\t" + (" " * 10) + "^"
    assert printed_lines[1] == expected_marker


def test_scanner_consecutive_symbols(new_names, create_definition_file):
    """Test tokenization of dense strings with no spacing."""
    content = "A=B.I1;"
    file_path = create_definition_file(content)
    scanner = Scanner(file_path, new_names)

    sym1 = scanner.get_symbol()
    assert sym1.type == scanner.NAME
    assert new_names.get_name_string(sym1.id) == "A"

    assert scanner.get_symbol().type == scanner.EQUALS

    sym3 = scanner.get_symbol()
    assert sym3.type == scanner.NAME
    assert new_names.get_name_string(sym3.id) == "B"

    assert scanner.get_symbol().type == scanner.DOT

    sym5 = scanner.get
