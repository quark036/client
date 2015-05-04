"""
Implements auto-reloading of python modules to be used for debugging.
"""

import sys, os
from importlib import reload

import logging
log = logging.getLogger(__name__)

from PyQt5.QtCore import QTimer

file_times = {}

def try_reload():
    "Searches for and reloads modified files."
    for name, mod in sys.modules.items():
        if hasattr(mod, '__file__'):
            mtime = os.stat(mod.__file__).st_mtime

            if mod in file_times and file_times[mod] != mtime:
                file_times[mod] = mtime

                log.info('Reloading %s.', name)
                reload(mod)

            file_times[mod] = mtime

_timer = None

def init():
    global _timer
    _timer = QTimer()
    _timer.timeout.connect(try_reload)
    _timer.start(5000)