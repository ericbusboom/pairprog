"""

"""
import argparse

import logging
import sys
from pathlib import Path
from typing import List
# noinspection PyUnresolvedReferences
import readline
import signal

import typesense
from pairprog import __version__
from pairprog.assistant import Assistant
from pairprog.objectstore import ObjectStore
from pairprog.tool import PPTools


from pairprog.assistant import logger as ass_logger


__author__ = "Eric Busboom"
__copyright__ = "Eric Busboom"
__license__ = "MIT"

_logger = logging.getLogger(__name__)

def parse_args(args):
    """Parse command line parameters

    Args:
      args (List[str]): command line parameters as list of strings
          (for example  ``["--help"]``).

    Returns:
      :obj:`argparse.Namespace`: command line parameters namespace
    """
    parser = argparse.ArgumentParser(description="Pair Programming Assistant")

    parser.add_argument(
        "-D",
        "--delete",
        help="Delete all documents in the library",
        action="store_true",
    )

    parser.add_argument(
        "-L",
        "--list",
        help="List documents in the library",
        action="store_true",
    )

    parser.add_argument(
        "-C",
        "--count",
        help="Count documents in the library",
        action="store_true",
    )

    parser.add_argument(
        "-E",
        "--export",
        help="Export documents in the library",
        action="store_true",
    )

    parser.add_argument(
        "-o",
        "--once",
        help="Just run the command line request; don't loop",
        action="store_true",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"pairprog {__version__}",
    )

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

    parser.add_argument(dest="prompt", help="Initial prompt", nargs='*', type=str)

    return parser.parse_args(args)


def setup_logging(loglevel):
    """Setup basic logging

    Args:
      loglevel (int): minimum loglevel for emitting messages
    """
    #logformat = "[%(asctime)s] %(levelname)s:%(name)s:%(message)s"
    logging.basicConfig( )
    ass_logger.setLevel(loglevel or logging.FATAL)

def init():
    rc = ObjectStore.new(name='barker_minio', bucket='agent')

    ts = typesense.Client(
        {
            "api_key": "xyz",
            "nodes": [{"host": "barker", "port": "8108", "protocol": "http"}],
            "connection_timeout_seconds": 1,
        }
    )

    tool = PPTools(ts, rc.sub('pptools'), Path('/Volumes/Cache/scratch'))

    assis = Assistant(tool, cache=rc)

    return assis

def signal_handler(sig, frame):
    print("\nExiting the program.")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

def main(args):
    """
    """
    args = parse_args(args)
    setup_logging(args.loglevel)

    assist = init()

    if args.delete:
        print(assist.tools.library.clear_collection())
        return
    elif args.list:
        for d in  assist.tools.library.list():
            print(f"{d['id']:>4s}:{d['chunk']:<05d} {d['title'][:20]:20s} {d.get('description','')[:50]:50s} {d.get('source','')[:15]}")
    elif args.count:
        print(assist.tools.library.count(),"documents")
        return
    elif args.export:
        for d in  assist.tools.library.list():
            print(d)
    elif args.prompt:

        line = ' '.join(args.prompt)
        while True:
            if line.strip():
                r = assist.run(line)
                if False: # When streaming, output is done in the run loop
                    print(r)
                else:
                    print()

            if args.once:
                break

            line = input('$> ')
            if line == 'stop':
                break


def run():
    """Calls :func:`main` passing the CLI arguments extracted from :obj:`sys.argv`

    This function can be used as entry point to create console scripts with setuptools.
    """
    main(sys.argv[1:])


if __name__ == "__main__":
    run()
