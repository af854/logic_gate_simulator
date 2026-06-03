Syntax specification
========================================

This document describes the GF2 circuit definition language using the simulator's
formal grammar. It is unlikely that you will have coded with this grammar before. The
format is straightforward: the scanner recognises names, numbers and symbols,
then the parser checks that the file follows the grammar rules shown here.

Overview
--------

A circuit definition file consists of one or more module definitions followed by
a top-level network definition. Modules are reusable blocks that can be
instantiated inside the top-level circuit or inside other modules.

The basic file structure is:

- optional ``MODULE`` definitions
- one top-level network defined with ``DEVICES``, ``CONNECT`` and ``MONITOR``

The top-level network may also include an optional ``NETS`` section.

Lexical elements
----------------

The grammar in GF2 is built from a small set of tokens.

- ``name`` is a sequence of letters, digits and underscore characters, starting
  with a letter.
- ``number`` is one or more digits.
- ``literal`` is either ``0`` or ``1``.
- Punctuation uses the symbols ``(``, ``)``, ``,`` and ``;``.

Names are used for device identifiers, module names, signal names and net names.
They are case-sensitive, and keywords such as ``DEVICES``, ``MODULE`` and
``CONNECT`` are written in uppercase in the examples.

File structure
--------------

A complete file follows this pattern:

.. code-block:: text

    { module }
    network

This means zero or more module definitions may appear before the top-level
network.

Module definition
-----------------

A module definition has the following structure:

.. code-block:: text

    MODULE <name>
    INPUTS <name>, <name>, ... ;
    OUTPUTS <name>, <name>, ... ;
    DEVICES
        <device> ;
        <device> ;
        ...
    [ NETS <name>, <name>, ... ; ]
    CONNECT
        <connect> ;
        ...
    ENDMODULE ;

The module body declares input and output ports, lists internal device
instances, optionally names nets, and specifies connections.

Top-level network
-----------------

The top-level network appears after any module definitions and has this form:

.. code-block:: text

    DEVICES
        <device> ;
        ...
    [ NETS <name>, <name>, ... ; ]
    CONNECT
        <connect> ;
        ...
    MONITOR
        <signal>, <signal>, ... ;

The top-level ``DEVICES`` section creates the actual circuit elements and
module instances used in the root design.

Device definitions
------------------

Each device declaration ends with a semicolon. There are three device kinds:

- parameterised devices: ``AND(2)``, ``NAND(2)``, ``OR(2)``, ``NOR(2)``,
  ``CLOCK(1)``, ``SWITCH(1)``
- fixed devices: ``DTYPE`` and ``XOR``
- module devices: any previously defined module name

The grammar for a device declaration is:

.. code-block:: text

    <device_kind> <name>, <name>, ... ;

Examples:

.. code-block:: text

    AND(2) A1, A2 ;
    DTYPE D0 ;
    MUX2 M0 ;

A module device uses the module name and may be instantiated with one or more
instance names.

Signals and sources
-------------------

Connections use signals and literals.

A signal is a name or a dotted pair of names:

.. code-block:: text

    <name>
    <name>.<name>

A dotted signal is used to refer to a specific port of a device instance. For
example, ``A1.I1`` means port ``I1`` of device ``A1``.

A source can be either a signal or a literal value:

.. code-block:: text

    0
    1
    A0
    M0.Y

Connection statements
---------------------

Each connection statement ends with a semicolon. The left-hand side is a list of
signals, and the right-hand side is a source. The signals on the left-hand side
are all driven by the source.

.. code-block:: text

    <signal>, <signal>, ... = <source> ;

Examples:

.. code-block:: text

    Q = D0.Q ;
    O1.I1 = A0 ;
    OUT = N ;
    X, Y = 1 ;

This means that every signal in the comma-separated list is connected to the
same source value.

Monitor section
---------------

The ``MONITOR`` section lists signals whose values are recorded during
simulation. The section ends with a semicolon.

.. code-block:: text

    MONITOR
        CLK, EN, OUT ;

Example: simple top-level file
------------------------------

A minimal circuit file looks like this:

.. code-block:: text

    DEVICES
        CLOCK(1) CLK ;
        SWITCH(1) SW ;
        AND(2) A ;
    CONNECT
        A.I1 = CLK ;
        A.I2 = SW ;
    MONITOR
        CLK, SW, A ;

This file defines a clock, a switch and an AND gate. It connects the gate inputs
and monitors the clock, switch and gate output.

Example: module definition
--------------------------

A simple module can be defined and reused in the top-level circuit:

.. code-block:: text

    MODULE NOT_GATE
    INPUTS IN ;
    OUTPUTS OUT ;
    DEVICES
        NAND(2) N ;
    CONNECT
        N.I1 = IN ;
        N.I2 = IN ;
        OUT = N ;
    ENDMODULE ;

    DEVICES
        NOT_GATE U1 ;
    CONNECT
        U1.IN = A ;
        OUT = U1 ;
    MONITOR
        A, OUT ;

This module defines a reusable inverter using a NAND gate and then instantiates
it in the top-level network.

Notes
-----

- The grammar in this document is the structural form of a valid file. The
  scanner and parser may also accept whitespace and comments that are not shown
  in the grammar rules.
- The ``NETS`` section is optional and is used to declare net names explicitly.
- The top-level file may contain zero or more module definitions before the
  main network.

Formal grammar summary
----------------------

The formal grammar rules are:

.. code-block:: text

    network_file = { module }, network ;

    network = "DEVICES", { device },
              ["NETS", { name_list, ";" }],
              "CONNECT", { connect },
              "MONITOR", { signal_list, ";" } ;

    module = "MODULE", name,
             "INPUTS", { name_list, ";" },
             "OUTPUTS", { name_list, ";" },
             "DEVICES", { device },
             ["NETS", { name_list, ";" }],
             "CONNECT", { connect },
             "ENDMODULE", ";" ;

    device = device_kind, name_list, ";" ;
    name_list = name, { ",", name } ;
    signal_list = signal, { ",", signal } ;

    device_kind = parameterised_device, "(", number, ")"
                 | fixed_device
                 | module_device ;

    parameterised_device = "AND" | "NAND" | "OR" | "NOR"
                         | "CLOCK" | "SWITCH" ;
    fixed_device = "DTYPE" | "XOR" ;
    module_device = name ;

    connect = signal_list, "=", source, ";" ;
    source = signal | literal ;

    signal = name, [ ".", name ] ;
    literal = "0" | "1" ;

    name = letter, { letter | digit | "_" } ;
    number = digit, { digit } ;
