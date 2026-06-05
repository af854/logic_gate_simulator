.. GF2 Logic Simulator documentation master file, created by
   sphinx-quickstart on Sun May 31 17:49:38 2026.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

GF2 Logic Simulator documentation
=================================

This documentation describes the GF2 Logic Simulator and explains how to use it.
It provides an overview of the simulator, the circuit definition language and
the project organisation.

The user guide contains practical instructions for running the simulator and
working with the example definition files. The syntax specification documents
the file grammar in a way that is friendly for readers who have not used EBNF
before.

Further pages describe the simulator subsystems: devices, the graphical
interface, monitors, network execution, parser implementation, scanner behaviour
and the text-based user interface.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   user_guide
   syntax_spec
   devices
   gui
   gui_3D
   monitors
   names
   network
   parse
   parser_objects
   scanner
   userint