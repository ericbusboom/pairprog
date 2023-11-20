import unittest
from pathlib import Path
from typing import Any
import json

import typesense
from pairprog.ipython import IpyKernel
from pairprog.objectstore import ObjectStore
from pairprog.util import generate_tools_specification
from .search import TextSearch


class Tool:
    """Baseclass for AI tool"""

    @classmethod
    def specification(cls):
        """Return the specification for the tools available in this class."""
        return generate_tools_specification(cls)
from pathlib import Path
from typesense import Client
from typing import Any

class PPTools(Tool):
    """Functions that the AI assistant can use to run python code, remember
    facts and store, search and retrieve documents.

    Attributes:
        ts_client (Client): Client to interact with the typesense server.
        os (ObjectStore): An object store for storing various objects.
        wd (Path): Working directory path.
        ipy (IpyKernel): An instance of IPython kernel.
        library (TextSearch): A text search engine.
    """

    def __init__(self,
                 typesense_client: Client,
                 object_store: ObjectStore,
                 working_dir: Path) -> None:
        self.ts_client = typesense_client
        self.os = object_store
        self.wd = working_dir

        self.ipy = IpyKernel()
        self.ipy.start()

        self.library = TextSearch(self.ts_client)

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
        mid, o = self.ipy.exec(code)
        return o

    def get_code_var(self, varname: str) -> Any:
        """Retrieve the value of a variable from the IPython kernel as JSON.

        Args:
            varname (str): Name of the variable.

        Returns:
            Any: JSON representation of the variable's value.
        """
        return self.ipy.get_var(varname)

    def remember(self, key: str, value: Any) -> None:
        """Store a value in the cache, associated with a key.

        Args:
            key (str): The key associated with the value.
            value (Any): The value to be stored.
        """
        self.os[key] = value

    def recall(self, key: str) -> Any:
        """Retrieve a value from the cache using its key.

        Args:
            key (str): The key associated with the value.

        Returns:
            Any: The value retrieved from the cache.
        """
        return self.os[key]

    def store_document(self, title: str, text: str, description: str = None,
                       source: str = None, tags: list[str] = None) -> dict:
        """Store a document in the library.

        Args:
            title (str): Title of the document.
            text (str): Text content of the document.
            description (str, optional): Description of the document.
            source (str, optional): Source of the document.
            tags (list[str], optional): List of tags associated with the document.

        Returns:
            dict: A dictionary with non-None arguments used in the document.
        """
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
        return self.library.get(key)

    def search_documents(self, query: str) -> list:
        """Search for documents in the library that match a given query.

        Args:
            query (str): The search query.

        Returns:
            list: A list of documents that match the query.
        """
        return self.library.search(query)

    def done(self) -> None:
        """Signal to the user that this session is completed."""

class TestCase(unittest.TestCase):
    def test_basic(self):

        rc = ObjectStore.new(bucket='test', class_='FSObjectStore', path='/tmp/cache')

        ts = typesense.Client(
            {
                "api_key": "xyz",
                "nodes": [{"host": "barker", "port": "8108", "protocol": "http"}],
                "connection_timeout_seconds": 1,
            }
        )

        tool = PPTools(ts, rc, Path('/tmp/working'))

        print(json.dumps(tool.specification(), indent=4))

if __name__ == "__main__":
    unittest.main()
