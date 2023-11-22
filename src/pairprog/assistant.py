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
import uuid
from datetime import datetime
from itertools import count
import os


logger = logging.getLogger(__name__)

# from pydantic import BaseModel, Field

def render_message_dict(m):
    from openai.types.chat.chat_completion_chunk import ChoiceDelta

    if isinstance(m, dict):
        pass
    elif isinstance(m, ChoiceDelta):
        m = m.model_dump()

    if 'function_call' in m:
        del m['function_call']

    if 'tool_calls' in m and not m['tool_calls']:
        del m['tool_calls']

    return m

class Assistant:
    def __init__(
            self,
            tool: Tool,
            working_directory: str = None, # Path to a working directory
            messages: List[dict[str, Any]] = None,
            model= "gpt-3.5-turbo-1106",
            cache: Optional[dict | ObjectStore] = None,
            token_limit: int = 6000,  # max number of tokens to submit in messages
    ):
        self.tools = tool  # Functions to call, and function definitions
        self.func_spec = tool.specification()

        self.messages = messages or []

        self.run_id = None

        self.responses = []
        self.model = model
        self.token_limit = token_limit
        self.tokenizer = tiktoken.encoding_for_model(self.model)

        self.session_id = datetime.now().isoformat()+'-'+str(uuid.uuid4())

        self.cache = resolve_cache(cache)
        self.session_cache = self.cache.sub("session/" + self.session_id)
        self.file_cache = self.session_cache.sub("files")

        self.wd = working_directory or os.getcwd()
        os.chdir(self.wd)
        self.tools.set_working_dir(self.wd)

        self.streaming = True

        self.client  = openai.OpenAI()

        self.iter_key = lambda v: f"/none/{v}"

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
    def last_content(self):
        """Return the last content"""

        return self.messages[-1].content

    def _limited_messages(self, messages= None):
        def get_content(m):
            try:
                return str(m.content) or ''
            except AttributeError :
                return str(m['content']) or ''

        if messages is None:
            messages = self.messages

        total = 0
        msg = []
        for m in reversed(messages):
            toks = len(self.tokenizer.encode(get_content(m)))

            if toks + total <= self.token_limit:
                total += toks
                if not isinstance(m, dict):
                    m = render_message_dict(m)
                msg.insert(0, m)
            else:
                break

        return msg

    @property
    def limited_messages(self):
        """return the tail of the messages array for a number of messages that
        is less than the token limit"""

        return self._limited_messages(self.messages)

    def stop(self):
        pass

    def complete_streaming(self, messages: List[dict[str, Any]], callback):

        r = self.client.chat.completions.create(
            messages=messages,
            tools=self.func_spec,
            model=self.model,
            stream=True
        )

        chunks = []
        messages = []
        deltas = []

        content = ''
        tool_calls = None
        for i, chunk in enumerate(r):
            #logger.debug(f"Streaming chunk #{i}: {chunk}")
            chunks.append(chunk)
            delta = chunk.choices[0].delta

            # Store the content of the message, which comes bit by bit.
            if delta is not None:
                content += delta.content if delta.content is not None else ''
                deltas.append(delta)

            # Tool calls are also streamed! But only the first one has a name
            chunk_tc = chunk.choices[0].delta.tool_calls

            if chunk_tc and len(chunk_tc) > 0:
                logger.debug(f"Tool calls chunk #{i}: {chunk_tc}")
                if chunk_tc[0].function.name is not None:
                    # Setup the initial tool calls
                    #assert i == 0, "Tool calls should only be in the first chunk"
                    tool_calls = chunk_tc
                else:
                    # Add a chunk to the arguments
                    for i, tc in enumerate(chunk_tc):
                        tool_calls[i].function.arguments += tc.function.arguments

            callback(delta)

        self.session_cache[self.iter_key('chunks')] = chunks

        message = deltas[0]
        message.content = content
        message.tool_calls = tool_calls

        logger.info(f'Tool calls {tool_calls}')

        resp = chunks[-1]
        resp.choices[0].message = message
        resp.choices[0].delta = None

        return message, resp

    def complete_blocking(self, messages):

        r = self.client.chat.completions.create(
            messages=messages,
            tools=self.func_spec,
            model=self.model,
            stream=False
        )

        message = r.choices[0].message

        return message, r


    def run(self, prompt: str | List[dict[str, Any]], streaming=True, **kwargs) -> str :
        """Run a  completion request loop"""

        if isinstance(prompt, str):
            self.messages.append({"role": "user", "content": prompt})
        else:
            self.messages.extend(prompt)

        logger.debug(f"Starting loop. {len(self.messages)}")
        logger.debug(f"Last prompt: {self.messages[-1]['content'][:100]}".replace('\n', ' '))

        for iteration in count():

            self.iter_key = lambda v: f"/loop/{v}/{iteration:03d}"

            self.session_cache['messages'] = self.messages
            self.session_cache['limited_messages'] = self.limited_messages

            logger.debug(f"Request {self.messages[-1]['content'][:100]}".replace('\n', ' '))

            self.session_cache[self.iter_key('pre')] = {
                'messages': self.messages,
                'limited_messages': self.limited_messages,
                'tools': self.func_spec,
            }

            def cb(delta):
                if delta.content:
                    print(delta.content, end='')

            if streaming:
                message, r = self.complete_streaming(self.limited_messages, cb)
            else:
                message, r = self.complete_blocking(self.limited_messages)

            finish_reason = r.choices[0].finish_reason
            logger.debug(f"Finish reason: {finish_reason}")
            logger.debug(f"Response: {message}")

            self.responses.append(r)
            self.messages.append(message)

            self.session_cache['messages'] = self.messages
            self.session_cache['responses'] = self.responses

            match finish_reason:
                case "stop" | "content_filter":
                    self.stop()
                    return self.last_content
                case "length":
                    self.stop()
                    return self.last_content
                case "function_call" | "tool_calls":
                    try:
                        self.call_function(r)
                    except Done:
                        self.stop()
                        return self.last_content

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

            m = {
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": tool_call.function.name,
                "content": None
            }

            self.session_cache[self.iter_key('tool_call')] = {**m, "when":"pre"}

            try:
                f = getattr(self.tools, tool_call.function.name)
                args = json.loads(tool_call.function.arguments)
                r = f(**args)
            except Exception as e:
                e_msg = f"Failed to call tool '{tool_call.function.name}' with args '{tool_call.function.arguments}': {e} "
                logger.error(e_msg)
                m['content'] = str(e_msg)
                self.messages.append(m)
                continue

            if not isinstance(r, str):
                r = json.dumps(r, indent=2)

            toks = len(self.tokenizer.encode(r))

            m['content'] = r
            self.session_cache[self.iter_key('tool_call')] = {**m, "when":"post"}

            logger.debug(f"Tool response ({toks} tokens): " + str(r)[:100].replace('\n',''))

            if toks > self.token_limit/2:
                r='ERROR: Response too long to return to model. Try to make it smaller'

            m['content'] = r
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

        tool = PPTools(ts, rc.sub('pptools'), Path('/tmp/working'))

        assis = Assistant(tool, cache=rc)

        assis.run("Hi, can you tell me what tools you have access to?")

        assis.run("What is the sum of the first five digits of pi?")

    def test_codeand_store(self):
        import typesense
        from pathlib import Path

        logging.basicConfig()
        logger.setLevel(logging.DEBUG)

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

        assis.run("Search your filesystem for information about eric")

if __name__ == "__main__":
    unittest.main()
