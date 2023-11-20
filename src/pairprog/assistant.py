import json
import unittest
from typing import List, Optional, Any
import logging
import openai
import tiktoken
from alive_progress import alive_bar
from .objectstore import ObjectStore, resolve_cache
from .tool import PPTools, Tool
from .tool import Done

logger = logging.getLogger(__name__)

# from pydantic import BaseModel, Field

def render_message_dict(m):

    try:
        d = m.choices[0].message.model_dump()
    except AttributeError:
        d = dict(**m)
        d['finish_reason'] = ''

    return d

class Assistant:
    def __init__(
            self,
            tool: Tool,
            messages: List[dict[str, Any]] = None,
            model= "gpt-3.5-turbo-1106",
            cache: Optional[dict | ObjectStore] = None,
            token_limit: int = 6000,  # max number of tokens to submit in messages
    ):
        self.tools = tool  # Functions to call, and function definitions
        self.func_spec = tool.specification()

        self.messages = messages or []

        self.cache = resolve_cache(cache)
        self.messages_cache = self.cache.sub("messages")

        self.run_id = None

        self.responses = []
        self.model = model
        self.token_limit = token_limit
        self.tokenizer = tiktoken.encoding_for_model(self.model)

    @property
    def cost(self):
        """Return the cost of all stored responses"""
        from .util import costs

        cost = 0
        for r in self.responses:
            sch = costs[r.model]
            cost += (
                    r.usage.prompt_tokens * sch[0] / 1000
                    + r.usage.completion_tokens / 1000 * sch[1]
            )

        return cost

    @property
    def limited_messages(self):
        """return the tail of the messages array for a number of messages that
        is less than the token limit"""

        def get_content(m):
            try:
                return str(m.content) or ''
            except AttributeError :
                return str(m['content']) or ''

        total = 0
        msg = []
        for m in reversed(self.messages):
            toks = len(self.tokenizer.encode(get_content(m)))

            if toks + total <= self.token_limit:
                total += toks
                msg.insert(0, m)
            else:
                break

        return msg

    def stop(self):
        pass

    def run(self, prompt: str | List[dict[str, Any]], **kwargs):
        """Run a  completion request loop"""
        import uuid
        from time import time

        client = openai.OpenAI()

        self.run_id = hex(int(time()))[2:] + "-" + str(uuid.uuid4())

        if isinstance(prompt, str):
            self.messages.append({"role": "user", "content": prompt})
        else:
            self.messages.extend(prompt)

        logger.debug(f"Starting loop. {len(self.messages)}")
        logger.debug(f"Last prompt: {self.messages[-1]['content'][:100]}".replace('\n', ' '))

        while True:
            try:
                self.messages_cache["request/" + self.run_id] = self.messages

                logger.debug(f"Request {self.messages[-1]['content'][:100]}".replace('\n', ' '))

                try:
                    r = None
                    r = client.chat.completions.create(
                        messages=self.limited_messages,
                        tools=self.func_spec,
                        model=self.model,
                    )
                except Exception as e:
                    logger.debug(e)
                    raise

                rcz = r.choices[0]
                message = rcz.message
                logger.debug(f"Response: {render_message_dict(r).get('content', '')}")
                self.responses.append(r)

                self.messages.append(message)
                self.messages_cache["response/" + self.run_id] = self.messages

            except Exception as e:
                print("!!!!!! EXCEPTION !!!!!!!")
                print("RUN ID", self.run_id)
                print(e)
                print("!!!!!! RESPONSE !!!!!!!")
                print(json.dumps(r.model_dump(), indent=2) if r is not None else "NO RESPONSE")
                print("!!!!!! MESSAGES !!!!!!!")
                for m in self.messages:
                    print(m)

                raise

            logger.debug(f"Finish reason: {rcz.finish_reason}")

            match rcz.finish_reason:
                case "stop" | "content_filter":
                    self.stop()
                    return
                case "length":
                    self.stop()
                    return
                case "function_call" | "tool_calls":
                    try:
                        self.call_function(r)
                    except Done:
                        self.stop()
                        return

                case "null":
                    pass  # IDK what to do here.

                case _:
                    logger.debug(f"Unknown finish reason: {rcz.finish_reason}")




                # Default Case


    def call_function(self, response):
        """Call a function references in the response, the add the function result to the messages"""

        tool_calls = response.choices[0].message.tool_calls

        logger.debug(f"Starting Tool calls: {tool_calls}")

        for tool_call in tool_calls:

            logger.debug(f"Tool call: " +tool_call.function.name)

            f = getattr(self.tools, tool_call.function.name)
            args = json.loads(tool_call.function.arguments)

            try:
                r = f(**args)
            except Exception as e:
                logger.debug(e)
                r = str(e)

            if not isinstance(r, str):
                r = json.dumps(r, indent=2)

            toks = len(self.tokenizer.encode(r))

            logger.debug(f"Tool response ({toks} tokens): " + str(r)[:100].replace('\n',''))

            if toks > self.token_limit/2:
                r='ERROR: Response too long to return to model. Try to make it smaller'

            m = {
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": tool_call.function.name,
                "content": r,
            }

            self.messages.append(m)


class MyTestCase(unittest.TestCase):
    def test_basic(self):
        import typesense
        from pathlib import Path

        logging.basicConfig()
        logger.setLevel(logging.DEBUG)

        #rc = ObjectStore.new(bucket='test', class_='FSObjectStore', path='/tmp/cache')

        rc = ObjectStore.new(name='barker_minio', bucket='agent')

        ts = typesense.Client(
            {
                "api_key": "xyz",
                "nodes": [{"host": "barker", "port": "8108", "protocol": "http"}],
                "connection_timeout_seconds": 1,
            }
        )

        tool = PPTools(ts, rc, Path('/tmp/working'))

        assis = Assistant(tool, cache=rc)

        assis.run("Hi, can you tell me what tools you have access to?")

        assis.run("What is the sum of the first five digits of pi?")

    def test_codeand_store(self):
        import typesense
        from pathlib import Path

        logging.basicConfig()
        logger.setLevel(logging.DEBUG)

        #rc = ObjectStore.new(bucket='test', class_='FSObjectStore', path='/tmp/cache')

        rc = ObjectStore.new(name='barker_minio', bucket='agent')

        ts = typesense.Client(
            {
                "api_key": "xyz",
                "nodes": [{"host": "barker", "port": "8108", "protocol": "http"}],
                "connection_timeout_seconds": 1,
            }
        )

        tool = PPTools(ts, rc, Path('/Volumes/Cache/cache/scratch'))

        assis = Assistant(tool, cache=rc)

        #assis.run("Write a python program to get 5 cat facts from https://catfact.ninja/facts, then store"
        #          " them as a document in the library")

        #assis.run("Eric busboom has a website at ericbusboom.com. What can you tell me about him?"
        #          "Hint: start by writing a program to get the html from the website.")

        assis.run("Search your filesystem for information about eric")

if __name__ == "__main__":
    unittest.main()
