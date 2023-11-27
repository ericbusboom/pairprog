import json
import os
import subprocess
import unittest
from functools import cached_property
from pathlib import Path
from typing import Any

import typesense
import wikipedia
from typesense import Client

from pairprog.filesystem import FSAccess
from pairprog.ipython import IpyKernel
from pairprog.objectstore import ObjectStore
from pairprog.util import generate_tools_specification
from .library import Library


class Tool:
    """Baseclass for AI tool"""

    exclude_methods = ['__init__', 'set_working_dir', 'set_assistant',
                       'set_session_cache', 'run_tool']

    def __init__(self, working_directory: Path | str = None) -> None:
        self.wd = None
        self.set_working_dir(working_directory)
        self.session_cache = None
        self.iteration_id = None
        self.assistant = None

    @classmethod
    def specification(cls):
        """Return the specification for the tools available in this class."""
        return generate_tools_specification(cls)

    def set_working_dir(self, working_directory):
        self.wd = Path(working_directory)
        # Change the working directory
        os.chdir(self.wd)

    def set_assistant(self, assistant):
        self.assistant = assistant

    def run_tool(self, name, args):
        f = getattr(self, name)
        args = json.loads(args)
        return f(**args)


class Done(Exception):
    """We're done with the session"""
    pass


class PPTools(Tool):
    """Functions that the AI assistant can use to run python code, remember
    facts and store, search and retrieve documents.

    """

    def __init__(self,
                 typesense_client: Client,
                 object_store: ObjectStore,
                 working_dir: Path) -> None:

        super().__init__(working_dir)

        self.ts_client = typesense_client
        self.os = object_store

        self.fs = FSAccess(self.wd)

    @cached_property
    def ipy(self) -> IpyKernel:
        """An instance of IPython kernel."""
        ipy = IpyKernel()
        ipy.start()
        return ipy

    @cached_property
    def library(self) -> Library:
        """A text search engine."""
        return Library(self.ts_client)

    def execute_code(self, code: str) -> Any:
        """Execute a code using the IPython kernel.

        The return will be the IPython display for the last line of the
        code. For more rigorous output, assign values you would want to
        return to a variable, then use the get_code_var() function to
        get a JSON representation.

        Args:
            code (str): The code to be executed.

        Returns:
            Any: Output of the executed code. To use this output, print
            the result for scalar values, or jump JSON for more complex values.

        """
        try:
            if self.assistant:
                self.assistant.session_cache[self.iteration_id + '/code'] = code
            mid, o = self.ipy.exec(code)
            v = self.ipy.get_var('_')
            return v
        except Exception as e:
            return str(e)

    def smarter(self, text: str):
        """Upgrade your intelligence to solve hard problems better. If you are
        having trouble with a problem, try this function."""

        self.assistant.model = 'gpt-4-1106-preview'
        return 'I am now smarter'

    def faster_and_cheaper(self, text: str):
        """If problems are not very hard, you can downgrade your inteligence
        to solve them faster and cheaper."""

        self.assistant.model = "gpt-3.5-turbo-1106"
        return 'I am now faster and cheaper'

    def shell(self, command: str):
        """
        Runs a shell command and captures both stdout and stderr.

        Args:
            command (str): The command to run.
        """

        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            # text=True
        )

        # Wait for the command to complete
        stdout, stderr = process.communicate()

        # Combine stdout and stderr
        output = stdout + stderr

        return output.decode('utf-8', 'replace')

    def web_search(self, query: str):
        """
        Search the web for a query.

        Args:
            query (str): The query string to search for.
        """
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            results = [r for r in ddgs.text(query, max_results=5)]
            return json.dumps(results, indent=2)

    def store_document(self, title: str = None, text: str = None,
                       description: str = None,
                       source: str = None, tags: list[str] = None) -> dict:
        """Store a document in the library.

        To store a large document, provide just its url as the source:

            store_document(source=url)

        To store a wikipedial page, get it's store_document_uri from the
        wikipedia_search tool and provide that as the source:

            store_document(source='wiki:25080699')

        Smaller documents, especially ones you've generated yourself,
        can be stored with the remaining arguments,

            store_document(title='my document', text='...long text...', source='self')

        Args:
            title (str): Title of the document.
            text (str): Text content of the document.
            description (str, optional): Description of the document.
            source (str, optional): Source of the document.
            tags (list[str], optional): List of tags associated with the document.

        Returns:
            dict: A dictionary with non-None arguments used in the document.
        """

        if source.startswith('wiki:'):
            _, pageid = source.split(':')
            page = wikipedia.page(pageid=int(pageid))
            text = page.content
            description = page.summary[:250]

        return self.library.add_document(
            title=title, text=text,
            description=description,
            source=source, tags=tags
        )

    def get_document(self, key: int) -> Any:
        """Retrieve a document from the library using its key.

        Args:
            key (int): The document id of the document.

        Returns:
            Any: The document retrieved from the library.
        """
        return self.library.get_document(key)

    def search_documents(self, query: str, result_number: int) -> dict:
        """Search for documents in the library that match a given query.

        To properly use this function, call it with a query and result_number=0,
        to get the first result. Then, call it again with the same query and result_number=1,
        increasing the result_number until you find the document you are looking for,
        or until the function returns None

        Args:
            query (str): The search query.
            result_number (int): (Optional) Which result document to return
        Returns:
            dict|None: A list of documents that match the query.
        """

        d = self.library.search(query)
        try:
            return d[result_number]
        except IndexError:
            return None

    def read(self, path: str, encoding=None) -> str:
        """
        Read text from a file.

        Args:
            path (str): The path to the file to be read.
            encoding (str, optional): The encoding to use for reading the file.

        Returns:
            str: The content of the file as a string.
        """
        return self.fs.read(path, encoding=encoding)

    def write(self, path: str, b: str, encoding=None) -> None:
        """
        Write text to a file.

        Args:
            path (str): The path to the file to be written.
            b (str): The text content to write to the file.
            encoding (str, optional): The encoding to use for writing the file.
        """
        self.fs.write(path, b, encoding=encoding)
        return f"wrote {len(b)} bytes to {path}"

    def wikipedia_search(self, term: str):
        """Return the names of wikipedia pages that match the search term

        """

        o = []
        for page in wikipedia.search(term, results=10):
            p = wikipedia.page(page, auto_suggest=False)
            o.append({
                'page_name': page,
                'pageid': p.pageid,
                'store_document_uri': f'wiki:{p.pageid}',
                'url': p.url,
                'summary': p.summary[:400]
            })

        return o

    def wikipedia_page(self, page_name: str):
        pass


class TestCase(unittest.TestCase):

    def test_tool_spec(self):
        tool = PPTools(None, None, Path('/Volumes/Cache/scratch'))
        print(json.dumps(tool.specification(), indent=2))

    def test_basic(self):
        rc = ObjectStore.new(bucket='test', class_='FSObjectStore', path='/tmp/cache')

        ts = typesense.Client(
            {
                "api_key": "xyz",
                "nodes": [{"host": "barker", "port": "8108", "protocol": "http"}],
                "connection_timeout_seconds": 1,
            }
        )

        tool = PPTools(ts, rc, Path('/Volumes/Cache/scratch'))

        # print(json.dumps(tool.specification(), indent=4))

        # Execute Code
        o = tool.execute_code("a='hello world'\na\n")
        o = tool.execute_code("print(a)")
        self.assertEqual(o.strip(), 'hello world')
        o = tool.get_code_var('a')
        self.assertEqual(o, 'hello world')

        o = tool.execute_code("sum(int(digit) for digit in str(3.14159)[:6].replace('.', ''))")
        v = tool.get_code_var('_')
        print("v=", v)

        # Search

        tool.store_document('Drinking Whiskey', 'Wishkey will make you more inteligent')
        tool.store_document('Cleaning your Ears',
                            'If you don\'t clean your ears, you will get cancer',
                            description='A medical article of grave importance to audiophiles')

        r = tool.search_documents("How to prevent fatal diseases")
        self.assertEqual(r[0]['title'], 'Cleaning your Ears')

    def test_shell(self):
        tool = PPTools(None, None, Path('/Volumes/Cache/scratch'))
        o = tool.execute_code("!ls")
        print(o)


if __name__ == "__main__":
    unittest.main()
