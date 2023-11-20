"""

"""
import argparse
import logging
import sys
from pathlib import Path
from typing import List

import typesense
from pairprog import __version__
from pairprog.assistant import Assistant
from pairprog.objectstore import ObjectStore
from pairprog.tool import PPTools

import atexit
import os
import readline


__author__ = "Eric Busboom"
__copyright__ = "Eric Busboom"
__license__ = "MIT"

_logger = logging.getLogger(__name__)


histfile = os.path.join(os.path.expanduser("~"), ".ppa-history")

try:
    readline.read_history_file(histfile)
    h_len = readline.get_current_history_length()
except FileNotFoundError:
    open(histfile, 'wb').close()
    h_len = 0

def save(prev_h_len, histfile):
    new_h_len = readline.get_current_history_length()
    readline.set_history_length(1000)
    readline.append_history_file(new_h_len - prev_h_len, histfile)

atexit.register(save, h_len, histfile)



def parse_args(args):
    """Parse command line parameters

    Args:
      args (List[str]): command line parameters as list of strings
          (for example  ``["--help"]``).

    Returns:
      :obj:`argparse.Namespace`: command line parameters namespace
    """
    parser = argparse.ArgumentParser(description="Just a Fibonacci demonstration")
    parser.add_argument(
        "--version",
        action="version",
        version=f"pairprog {__version__}",
    )
    parser.add_argument(dest="n", help="n-th Fibonacci number", type=int, metavar="INT")
    parser.add_argument(
        "-v",
        "--verbose",
        dest="loglevel",
        help="set loglevel to INFO",
        action="store_const",
        const=logging.INFO,
    )
    parser.add_argument(
        "-vv",
        "--very-verbose",
        dest="loglevel",
        help="set loglevel to DEBUG",
        action="store_const",
        const=logging.DEBUG,
    )
    return parser.parse_args(args)


def setup_logging(loglevel):
    """Setup basic logging

    Args:
      loglevel (int): minimum loglevel for emitting messages
    """
    logformat = "[%(asctime)s] %(levelname)s:%(name)s:%(message)s"
    logging.basicConfig(
        level=loglevel, stream=sys.stdout, format=logformat, datefmt="%Y-%m-%d %H:%M:%S"
    )


def main(args):
    """
    """
    args = parse_args(args)
    setup_logging(args.loglevel)

    rc = ObjectStore.new(name='barker_minio', bucket='agent')

    ts = typesense.Client(
        {
            "api_key": "xyz",
            "nodes": [{"host": "barker", "port": "8108", "protocol": "http"}],
            "connection_timeout_seconds": 1,
        }
    )

    tool = PPTools(ts, rc, Path('/Volumes/Cache/scratch'))

    assis = Assistant(tool, cache=rc)

    assis.run("Search your filesystem for information about eric")


def run():
    """Calls :func:`main` passing the CLI arguments extracted from :obj:`sys.argv`

    This function can be used as entry point to create console scripts with setuptools.
    """
    main(sys.argv[1:])


if __name__ == "__main__":
    run()
