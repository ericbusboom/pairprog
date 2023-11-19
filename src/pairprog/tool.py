from typing import Any

import typesense

from pairprog.util import generate_tools_specification


class Tool:
    """Baseclass for AI tool"""

    @classmethod
    def tools(cls):
        """Return the specification for the tools available in this class."""
        return generate_tools_specification(cls)


class PPTools(Tool):
    def __init__(self, client: typesense.Client):
        self.client = client

    def call_ipython(self, code: str):
        """Call the IPython kernel with the given code"""
        from IPython import get_ipython

        ip = get_ipython()
        return ip.run_cell(code)

    def remember(self, key: str, value: Any):
        """Remember a value by storing it in the cache, associated with a key"""
        self.cache[key] = value

    def recall(self, key: str):
        """Recall a value from the cache, using its key"""
        return self.cache[key]

    def write_to_library(self, key: str, value: Any):
        """Write a value to the library"""
        self.library.set(key, value)

    def read_from_library(self, key: str):
        """Read a value from the library"""
        return self.library.get(key)

    def search_library(self, query: str):
        """Search the library"""
        return self.library.search(query)
