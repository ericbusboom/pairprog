import logging
import unittest
from os import environ

import typesense
from typesense.exceptions import ObjectAlreadyExists

logger = logging.getLogger(__name__)


class TextSearch:
    def __init__(self, client: typesense.Client | None = None):
        if client is None:
            self.client = typesense.Client(
                {
                    "api_key": "xyz",
                    "nodes": [{"host": "barker", "port": "8108", "protocol": "http"}],
                    "connection_timeout_seconds": 1,
                }
            )
        else:
            self.client = client

    library_schema = {
        "name": "library",
        "fields": [
            {"name": "title", "type": "string"},
            {"name": "description", "type": "string"},
            {"name": "source", "type": "string", "optional": True},
            {"name": "chunk", "type": "int32", "optional": True},
            {"name": "tags", "type": "string[]", "optional": True},
            {"name": "text", "type": "string"},
            {
                "name": "embedding",
                "type": "float[]",
                "embed": {
                    "from": ["text"],
                    "model_config": {
                        "model_name": "openai/text-embedding-ada-002",
                        "api_key": environ.get("OPENAI_API_KEY"),
                    },
                },
            },
        ],
    }

    def _create_collection(self, sch, delete=False):
        logger.debug(f"Loading {sch['name']} schema")

        try:
            self.client.collections.create(sch)
        except ObjectAlreadyExists:
            if delete:
                logger.debug(
                    f"Collection {sch['name']} already exists, deleting and recreating"
                )
                self.client.collections[sch["name"]].delete()
                self.client.collections.create(sch)
            else:
                logger.debug(f"Collection {sch['name']} already exists, skipping")
                return

    def create_collection(self, delete=False):
        """Create a collection with the given name and schema"""
        self._create_collection(self.library_schema, delete=delete)

    def add_document(self, doc):
        if "id" in doc:
            self.client.collections["library"].documents.upsert(id)
        else:
            self.client.collections["library"].documents.create(doc)

    def search(self, text, tags=None):
        """Search the collection for a given query"""

        query = {"q": text, "query_by": "description,embedding", "prefix": False}

        return self.client.collections["library"].documents.search(query)


class TestCase(unittest.TestCase):
    def test_basic(self):
        ts = TextSearch()

        ts.create_collection(delete=True)

        ts.add_document(
            {
                "title": "Software Engineer",
                "description": "I am a software engineer.",
                "tags": ["software", "engineer"],
                "text": "I am a software engineer.",
            }
        )

        ts.add_document(
            {
                "title": "PockiWoki",
                "description": "Just nonsense",
                "tags": ["software", "engineer"],
                "text": "Small rusted rabbits knit furiously in the night.",
            }
        )

        def p(r):
            for e in r["hits"]:
                d = e["document"]
                del d["embedding"]
                print(e["vector_distance"], d)

        r = ts.search("rodents make sweaters")
        p(r)


if __name__ == "__main__":
    unittest.main()
