User guide
==========

Introduction
------------

GF2 is a minimal logic simulator for digital circuits. It reads a text-based circuit definition file, constructs a network of connected devices and lets the user interact with that network through either a graphical interface or a command-line session.

The simulator is intended for learning, experimentation and simple circuit validation. It supports a collection of common device types and provides signal monitoring to inspect circuit behaviour over time.

Getting started
---------------

Running the simulator
^^^^^^^^^^^^^^^^^^^^^

Use one of the following commands from the repository root:

- ``python logsim.py`` to start the graphical interface.
- ``python logsim.py <path/to/circuit.txt>`` to open a circuit file in the graphical interface.
- ``python logsim.py -c <path/to/circuit.txt>`` to start the command-line interface.

If no file path is provided, the graphical interface opens with a blank state and prompts the user to load a circuit.

Circuit definition files
------------------------

Circuit files are written in the simulator's custom text format. They describe devices, nets, connections and monitors using a small set of recognised keywords.

The parser validates the file according to the grammar defined in ``logsim/syntax.ebnf``. The supported device types include ``CLOCK``, ``SWITCH``, ``AND``, ``NAND``, ``OR``, ``NOR``, ``XOR``, ``DTYPE`` and ``MODULE``.

Each device is connected by named nets. The simulator resolves these net names into an internal network representation, and monitors may be attached to nets to record signal values during simulation.

Quick start
------------------------------

The repository includes two example circuit definition files in ``logsim/example_definition_files``. These are intended to help you explore the simulator quickly and to demonstrate different uses of the definition language.

- ``stopwatch.txt`` is a compact sequential circuit that builds a dual-edge flop and ring counters. It shows how to define nested modules, instantiate devices such as ``DTYPE`` and ``NAND``, and connect nets for a simple timing circuit.
- ``traffic.txt`` is a more complete example of a traffic light controller. It includes comments and reusable modules such as a 2-bit subtractor, a countdown timer, a two-state finite-state machine, and a clock gating circuit. It demonstrates the language's support for module hierarchy, combinational logic and stateful devices.

To try the examples, open one directly from the repository root:

- ``python logsim.py logsim/example_definition_files/stopwatch.txt``
- ``python logsim.py logsim/example_definition_files/traffic.txt``

For the command-line interface, use the same files with the ``-c`` option:

- ``python logsim.py -c logsim/example_definition_files/stopwatch.txt``

These examples are a good starting point for understanding how the simulator maps definitions to live circuit behaviour.

Using the graphical interface
-----------------------------

The graphical interface displays the loaded circuit and allows the user to control simulation execution. Open a circuit from the File menu if one is not already loaded.

The GUI provides access to signal monitors, waveform tracing and step-by-step simulation. It is the recommended mode for visual inspection of circuit behaviour.

Using the command-line interface
-------------------------------

The command-line interface is useful for scripted use and for environments without a graphical display. It provides text-based interaction with the loaded circuit and lets the user control simulation cycles directly.

Project organisation
--------------------

The main entry point is ``logsim.py``. The simulator is organised into a set of focused modules:

- ``names`` for symbol table management and name resolution.
- ``scanner`` for lexical analysis of the circuit definition file.
- ``parse`` for syntactic and semantic analysis.
- ``devices`` for device definitions and behaviour.
- ``network`` for building and executing the simulated network.
- ``monitors`` for tracking signal history.
- ``gui`` for the wxPython graphical user interface.
- ``userint`` for the text-based command line interface.

Further reading
---------------

For details on the file grammar and accepted syntax, see ``syntax_spec.rst``. Other documentation pages describe simulator subsystems.

