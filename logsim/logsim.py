#!/usr/bin/env python3
"""Parse command line options and arguments for the Logic Simulator.

This script parses options and arguments specified on the command line, and
runs either the command line user interface or the graphical user interface.

Usage
-----
Show help: logsim.py -h
Command line user interface: logsim.py -c <file path>
Graphical user interface: logsim.py <file path>
Blank graphical user interface: logsim.py
"""
import getopt
import os
import sys

import wx

from names import Names
from devices import Devices
from network import Network
from monitors import Monitors
from scanner import Scanner
from parse import Parser
from userint import UserInterface
from gui import Gui, set_gui_language


def get_start_language():
    """Return the GUI language to use when the program starts."""
    environment_language = os.environ.get("LANG", "").lower().replace("-", "_")
    if environment_language.startswith("ar"):
        return "ar"
    if environment_language.startswith("en"):
        return "en"

    system_language = wx.Locale.GetSystemLanguage()
    language_info = wx.Locale.GetLanguageInfo(system_language)
    if language_info is not None:
        system_language_name = language_info.CanonicalName.lower()
        if system_language_name.startswith("ar"):
            return "ar"

    return "en"


def initialise_locale():
    """Initialise wx translations for the GUI and keep the locale alive."""
    set_gui_language(get_start_language())


def main(arg_list):
    """Parse the command line options and arguments specified in arg_list.

    Run either the command line user interface, the graphical user interface,
    or display the usage message.
    """
    usage_message = ("Usage:\n"
                     "Show help: logsim.py -h\n"
                     "Command line user interface: logsim.py -c <file path>\n"
                     "Graphical user interface: logsim.py <file path>\n"
                     "Blank graphical user interface: logsim.py")
    try:
        options, arguments = getopt.getopt(arg_list, "hc:")
    except getopt.GetoptError:
        print("Error: invalid command line arguments\n")
        print(usage_message)
        sys.exit()

    # Initialise instances of the four inner simulator classes
    names = Names()
    devices = Devices(names)
    network = Network(names, devices)
    monitors = Monitors(names, devices, network)
    # names = None
    # devices = None
    # network = None
    # monitors = None

    for option, path in options:
        if option == "-h":  # print the usage message
            print(usage_message)
            sys.exit()
        elif option == "-c":  # use the command line user interface
            scanner = Scanner(path, names)
            parser = Parser(names, devices, network, monitors, scanner)
            if parser.parse_network():
                # Initialise an instance of the userint.UserInterface() class
                userint = UserInterface(names, devices, network, monitors)
                userint.command_interface()

    if not options:  # no option given, use the graphical user interface

        if len(arguments) > 1:  # wrong number of arguments
            print("Error: at most one file path may be given\n")
            print(usage_message)
            sys.exit()

        # Small change by Arwa to allow the gui to open without a file path argument (it'll show a status message in that case)
        app = wx.App()
        initialise_locale()
        if len(arguments) == 1:
            [path] = arguments
            scanner = Scanner(path, names)
            parser = Parser(names, devices, network, monitors, scanner)
            if parser.parse_network():
                # Initialise an instance of the gui.Gui() class
                gui = Gui("Logic Simulator", path, names, devices, network,
                          monitors, parser.net_driver_dict)
                # Tiny change by Kevin, pass net_driver_dict to GUI
            else:
                sys.exit()
        else:
            gui = Gui("Logic Simulator", None, names, devices, network,
                      monitors, {})
            gui.show_status(
                wx.GetTranslation("No circuit loaded. Use File > Open to load one.")
            )

        gui.Show(True)
        app.MainLoop()


if __name__ == "__main__":
    main(sys.argv[1:])
