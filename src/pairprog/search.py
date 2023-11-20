import logging
import unittest
from os import environ

import typesense
from typesense.exceptions import ObjectAlreadyExists

logger = logging.getLogger(__name__)


class TextSearch:
    def __init__(self, client: typesense.Client | None):
        self.client = client

    library_schema = {
        "name": "library",
        "fields": [
            {"name": "title", "type": "string"},
            {"name": "description", "type": "string", "optional": True},
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

    def clear_collection(self):
        """Clear the collection"""
        self.client.collections["library"].documents.delete({"filter_by": "id:*"})


    def _add_document(self, doc):
        if "id" in doc:
            r =  self.client.collections["library"].documents.upsert(id)
        else:
            r =  self.client.collections["library"].documents.create(doc)

        if 'embedding' in r:
            del r['embedding']

        return r

    # Add a document from function arguments
    def add_document(self, title: str, text: str, description=None, source=None, chunk=None, tags=None):
        """
        Create a dictionary with the given arguments, excluding any that are None.

        :param title: Title of the item (string)
        :param description: Description of the item (string)
        :param source: Source of the item (string, optional)
        :param chunk: Chunk number (int, optional)
        :param tags: List of tags (list of strings, optional)
        :param text: Text content (string)
        :return: Dictionary with non-None arguments
        """
        args = {
            "title": title,
            "description": description,
            "source": source,
            "chunk": chunk,
            "tags": tags,
            "text": text
        }
        # Exclude keys with None values
        doc = {k: v for k, v in args.items() if v is not None}

        return self._add_document(doc)

    def _search(self, text, tags=None):
        """Search the collection for a given query"""

        query = {"q": text,
                 "query_by": "title, description,embedding",
                 "prefix": False,
                 "exclude_fields" : "embedding"}

        r = self.client.collections["library"].documents.search(query)

        return r

    def search(self, text, tags=None):

        r = self._search(text)

        hits = []
        # Consoldate some of the results fields
        for h in r['hits']:

            tmi = h['text_match_info']
            tmi['rank_fusion_score'] = h['hybrid_search_info']['rank_fusion_score']
            del h['hybrid_search_info']
            tmi['text_match'] = h['text_match']
            del h['text_match']
            tmi['vector_distance'] = h['vector_distance']
            del h['vector_distance']

            doc = h['document']
            doc['_text_match_info'] = tmi

            hits.append(doc)

        return hits


    def get_document(self, doc_id):
        d = self.client.collections['library'].documents[doc_id].retrieve()
        if 'embedding' in d:
            del d['embedding']

        return d

class TestCase(unittest.TestCase):

    def setUp(self):
        self.client = typesense.Client(
            {
                "api_key": "xyz",
                "nodes": [{"host": "barker", "port": "8108", "protocol": "http"}],
                "connection_timeout_seconds": 1,
            }
        )

    def test_basic(self):
        ts = TextSearch(self.client)

        ts.create_collection(delete=True)

        ts._add_document(
            {
                "title": "Software Engineer",
                "description": "I am a software engineer.",
                "tags": ["software", "engineer"],
                "text": "I am a software engineer.",
            }
        )

        r = ts._add_document(
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

        r = ts.search("do more web programming")
        self.assertEqual(r[0]['id'],"Software Engineer")

        r = ts.search("rodents make sweaters")
        self.assertEqual(r[0]['id'],  "PockiWoki")

    def test_add_doc(self):
        ts = TextSearch(self.client)
        ts.create_collection(delete=True)

        ts.add_document('Drinking Whiskey', 'Wishkey will make you more inteligent')
        ts.add_document('Cleaning your Ears',
                        'If you don\'t clean your ears, you will get cancer',
                        description='A medical article of grave importance to audiophiles')

        r = ts.search("How to prevent fatal diseases")
        import json
        print(json.dumps(r, indent=4))

if __name__ == "__main__":
    unittest.main()
