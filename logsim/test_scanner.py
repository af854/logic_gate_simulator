"""Test the scanner module.

Used in the Logic Simulator project to comprehensively test the Scanner
and Symbol classes using pytest.

Tests cover initialization, file handling, lexical tokenization (punctuation,
numbers, keywords, user names), comment/whitespace skipping, line tracking,
and error reporting.
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
        file_path.write_text(content)
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

    # Should skip the @, #, and ! and go straight to the number
    sym = scanner.get_symbol()
    assert sym.type == scanner.NUMBER
    assert sym.id == 42


def test_scanner_eof(new_names, create_definition_file):
    """Test that the EOF symbol is correctly generated at file termination."""
    file_path = create_definition_file("")
    scanner = Scanner(file_path, new_names)

    sym = scanner.get_symbol()
    assert sym.type == scanner.EOF


def test_scanner_line_tracking(new_names, create_definition_file):
    """Test that line numbers and column positions are rigorously tracked."""
    content = "A = 12;\n(* skip \n me *)\nB"
    file_path = create_definition_file(content)
    scanner = Scanner(file_path, new_names)

    # Line 0: "A = 12;"
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

    # Line 3: "B" (0-indexed array so line 4 visually)
    sym_b = scanner.get_symbol()
    assert sym_b.line_num == 3
    assert sym_b.line_pos == 0


def test_scanner_print_error_line(new_names, create_definition_file, capsys):
    """Test the visual layout and dynamic padding of the error marker."""
    content = "CONNECT A = B.I1;"
    file_path = create_definition_file(content)
    scanner = Scanner(file_path, new_names)

    # Manually trigger an error pointer on the '=' sign (index 10)
    scanner.print_error_line(0, 10)

    captured = capsys.readouterr()
    printed_lines = captured.out.split("\n")

    # The first printed line should be the file text
    assert printed_lines[0] == content
    # The second line should contain 10 spaces followed by the marker
    expected_marker = " " * 10 + "^"
    assert printed_lines[1] == expected_marker
