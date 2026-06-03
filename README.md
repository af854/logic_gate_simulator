# Project GF2: Logic Simulator

GF2 is a Python logic simulator for both combinatorial and clocked digital circuits. It reads a simple text-based circuit definition file, constructs the corresponding network, and then lets the user interact with that network either through a graphical interface or a command-line session.

The simulator is designed to make it easy to define devices such as `CLOCK`, `SWITCH`, `AND`, `NAND`, `OR`, `NOR`, `XOR`, `DTYPE`, and `MODULE`, and to connect them using named nets. It supports signal monitoring, waveform tracing and step-by-step execution of simulation cycles.

## Getting started

### Prerequisites

- Python 3.8 or later
- `wxPython` for the graphical user interface
- `PyOpenGL` for waveform rendering
- `pytest` for running the unit tests

The project also includes Sphinx dependencies in `requirements.txt` for building the documentation.

### Running the simulator

Open a terminal in the repository root and use one of the following commands:

- Launch the GUI:

```bash
python logsim.py
```

- Launch the GUI and load a circuit file directly:

```bash
python logsim.py <path/to/circuit.txt>
```

- Launch the command-line interface:

```bash
python logsim.py -c <path/to/circuit.txt>
```

If you run `python logsim.py` without a file path, the GUI starts with a blank state and allows you to open a file from the menu.

## Circuit definition language

Circuit files are written in a custom text format that describes devices and connections in sections such as `DEVICES`, `NETS`, `CONNECT`, and `MONITOR`.

The parser uses an EBNF grammar defined in `logsim/syntax.ebnf` and a fallback grammar in `logsim/fallback/fallback_syntax.ebnf`. This grammar governs the recognised keywords, identifiers, punctuation and comment styles.

## Project organisation

The simulator is split into a set of focused modules:

- `names` handles symbol table management and maps strings to unique integer IDs.
- `scanner` performs lexical analysis of the definition file.
- `parse` carries out syntactic and semantic analysis to build the circuit.
- `gui` provides the wxPython graphical interface and waveform display.
- `devices` defines the behaviour of the available circuit elements.
- `network` constructs and executes the simulated network.
- `monitors` stores signal trace history and manages monitor state.
- `userint` implements the text-based command-line interface.

The main entry-point is `logsim.py`, which initialises the simulator components and selects either the GUI or the CLI based on command-line arguments.

## Testing

Run the unit tests with verbose output using:

```bash
pytest -v
```

Integration test definition files are provided in `logsim/test_definition_files/`.

## Documentation and style

The project follows PEP 8 for code style and PEP 257 for docstrings. Documentation source files are stored under `docs/source/`, and built HTML documentation is available in `docs/build/html/`.

For online documentation, see:

- `https://ibrahim-nur.github.io/GF2/`

## Authors

Copyright © Ibrahim Nur, Kevin Liu and Arwa Fathy.