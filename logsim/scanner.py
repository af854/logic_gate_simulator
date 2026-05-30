"""Read the circuit definition file and translate the characters into symbols.

Used in the Logic Simulator project to read the characters in the definition
file and translate them into symbols that are usable by the parser.

Classes
-------
Scanner - reads definition file and translates characters into symbols.
Symbol - encapsulates a symbol and stores its properties.
"""

import bisect
import re
import sys


class Symbol:
    """Encapsulate a symbol and store its properties.

    Parameters
    ----------
    symbol_type : int, optional
        The integer representing the token category (e.g., NAME, NUMBER).
    symbol_id : int, optional
        The unique integer ID from the Names class, or the numerical value.
    line_num : int, optional
        The line index in the definition file where the symbol begins.
    line_pos : int, optional
        The column index in the definition file where the symbol begins.
    """

    __slots__ = ["type", "id", "line_num", "line_pos"]

    def __init__(self, symbol_type=None, symbol_id=None, line_num=None, line_pos=None):
        """Initialise symbol properties."""
        self.type = symbol_type
        self.id = symbol_id
        self.line_num = line_num
        self.line_pos = line_pos


class Scanner:
    """Read circuit definition file and translate the characters into symbols.

    Parameters
    ----------
    path : str
        Path to the circuit definition file.
    names : Names
        Instance of the names.Names() class for mapping strings to IDs.

    Methods
    -------
    get_symbol()
        Translates the next sequence of characters into a symbol.
    print_error_line(line_num, line_pos)
        Prints the specified line and places a marker below the error position.
    """

    def __init__(self, path, names):
        """Open specified file and initialise reserved words and IDs."""
        self.names = names

        (
            self.COMMA,
            self.SEMICOLON,
            self.EQUALS,
            self.DOT,
            self.L_BRACKET,
            self.R_BRACKET,
            self.KEYWORD,
            self.NUMBER,
            self.NAME,
            self.EOF,
            self.UNKNOWN
        ) = range(11)

        self.punct_map = {
            ",": self.COMMA,
            ";": self.SEMICOLON,
            "=": self.EQUALS,
            ".": self.DOT,
            "(": self.L_BRACKET,
            ")": self.R_BRACKET,
        }

        keyword_list = [
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
        ]

        keyword_ids = self.names.lookup(keyword_list)
        self.keyword_map = dict(zip(keyword_list, keyword_ids))

        try:
            with open(path, "r") as f:
                self._text = f.read()
        except OSError as e:
            print(f"Error opening file '{path}': {e}")
            sys.exit(1)

        # Cache lines for instant error reporting
        self.lines = self._text.split("\n")

        self.line_starts = [0]
        for i, char in enumerate(self._text):
            if char == "\n":
                self.line_starts.append(i + 1)

        regex_pattern = (
            r"(?P<COMMENT>\(\*.*?\*\)|#[^\n]*)|"  # EBNF and Python style comments
            r"(?P<WHITESPACE>\s+)|"  # Matches spaces, tabs, newlines
            r"(?P<NUMBER>\d+)|"  # Matches sequences of digits
            r"(?P<NAME>[A-Za-z][A-Za-z0-9_]*)|"  # Matches identifiers & keywords
            r"(?P<PUNCTUATION>[=,;.()])|"  # Matches valid EBNF punctuation
            r"(?P<UNKNOWN>.)"  # Fallback for illegal characters
        )

        # re.DOTALL ensures the comment regex can span across multiple lines
        self.regex = re.compile(regex_pattern, re.DOTALL)
        self.iterator = self.regex.finditer(self._text)

    def get_symbol(self):
        """Translate the next sequence of characters into a symbol.

        Returns
        -------
        Symbol
            An instance of the Symbol class representing the extracted token.
            Returns an EOF symbol when the end of the file is reached.
        """
        while True:
            match = next(self.iterator, None)

            if match is None:
                pos = len(self._text)
                line_num = bisect.bisect_right(self.line_starts, pos) - 1
                line_pos = pos - self.line_starts[line_num]
                return Symbol(self.EOF, None, line_num, line_pos)

            group = match.lastgroup

            if group in ("WHITESPACE", "COMMENT"):
                continue


            start_index = match.start()
            line_num = bisect.bisect_right(self.line_starts, start_index) - 1
            line_pos = start_index - self.line_starts[line_num]

            if group == "UNKNOWN":
                return Symbol(self.UNKNOWN, None, line_num, line_pos)

            string_val = match.group()

            if group == "PUNCTUATION":
                sym_type = self.punct_map[string_val]
                return Symbol(sym_type, None, line_num, line_pos)

            elif group == "NUMBER":
                return Symbol(self.NUMBER, int(string_val), line_num, line_pos)

            elif group == "NAME":
                if string_val in self.keyword_map:
                    sym_id = self.keyword_map[string_val]
                    return Symbol(self.KEYWORD, sym_id, line_num, line_pos)
                else:
                    [sym_id] = self.names.lookup([string_val])
                    return Symbol(self.NAME, sym_id, line_num, line_pos)

    def print_error_line(self, line_num, line_pos):
        """Print the input line along with a marker indicating the error position.

        Parameters
        ----------
        line_num : int
            The index of the line containing the error.
        line_pos : int
            The column index where the error occurred.
        """
        if 0 <= line_num < len(self.lines):
            line = self.lines[line_num]
            print(line)
            marker_padding = "".join(
                "\t" if char == "\t" else " " for char in line[:line_pos]
            )
            print(marker_padding + "^")
