# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

import os
import sys

sys.path.insert(0, os.path.abspath("../../logsim"))

project = "GF2 Logic Simulator"
copyright = "2026, Ibrahim Nur, Kevin Liu, Arwa Fathy"
author = "Ibrahim Nur, Kevin Liu, Arwa Fathy"
release = "0.1.0-alpha"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",  # adds support for Google/NumPy style docstrings
    "sphinx.ext.viewcode",  # adds links to the highlighted source code
    "sphinx_rtd_dark_mode",
]

templates_path = ["_templates"]
exclude_patterns = []


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
html_show_sphinx = False
html_css_files = [
    "custom.css",
]
html_js_files = [
    "custom.js",
]
if os.environ.get("CI"):
    autodoc_mock_imports = ["wx", "OpenGL"]
