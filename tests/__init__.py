"""Test package.

This file exists so that `tests` is a package and the suite can do
`from .conftest import make_view`. Without it every module using that import
fails to collect with "attempted relative import with no known parent
package".

It has a docstring rather than being empty because a zero-byte file is easily
lost in transit - skipped by a download, dropped by a copy - and its absence
shows up as five import errors that look nothing like a missing file.
"""
