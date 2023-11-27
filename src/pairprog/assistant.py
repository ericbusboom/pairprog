import json
import logging
import os
import unittest
import uuid
from copy import deepcopy
from datetime import datetime
from itertools import count
from pathlib import Path
from typing import List, Optional, Any

import openai
import tiktoken

from .objectstore import ObjectStore, resolve_cache
from .tool import Done
from .tool import PPTools, Tool

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


class History:

    def __init__(self, messages):
        pass


class Assistant:
    def __init__(
            self,
            tool: Tool,
            working_directory: str = None,  # Path to a working directory
            messages: List[dict[str, Any]] = None,
            model="gpt-3.5-turbo-1106",
            cache: Optional[dict | ObjectStore] = None,
            token_limit: int = None,  # max number of tokens to submit in messages
    ):
        self.tools = tool  # Functions to call, and function definitions
        self.tools.set_assistant(self)
        self.func_spec = tool.specification()

        self.messages = messages or []
        self.responses = []
        self.chunks = []

        self.run_id = None

        self.models = None
        self.model, self.token_limit = self.select_model(model, token_limit)

        self.tokenizer = tiktoken.encoding_for_model(self.model)

        self.session_id = datetime.now().isoformat() + '-' + str(uuid.uuid4())

        self.cache = resolve_cache(cache)
        self.session_cache = self.cache.sub("session/" + self.session_id)
        self.file_cache = self.session_cache.sub("files")

        self.wd = working_directory or os.getcwd()
        os.chdir(self.wd)
        self.tools.set_working_dir(self.wd)

        self.client = openai.OpenAI()

        self.iter_key = lambda v: f"/none/{v}"

        self.system = {
            'role': 'system',
            'content': Path(__file__).parent.joinpath('system.txt').read_text()
        }

    def select_model(self, model, token_limit):
        """Resolve sort model codes to model names, and return the model name and token limit"""

        models_json = Path(__file__).parent.joinpath('models.json').read_text()
        models = json.loads(models_json)

        self.models = {m['model_name']: m for m in models}

        if str(model) == '3.5':
            model = "gpt-3.5-turbo-1106"
        elif str(model) == '4':
            model = "gpt-4-32k"

        d = self.models[model]

        return d['model_name'], token_limit or (d['context_window'] - d['output_tokens'])

    def display(self, m):
        """Display a message to the user"""
        print(m)

    @property
    def last_content(self):
        """Return the last content"""

        return self.messages[-1]

    def request_messages(self, messages=None, max_tokens=None, elide_args=True):
        """Return a set of request messages that are less than the token limit, and
        perform some other editing, such as eliding the arguments form tool requests"""
        if max_tokens is None:
            max_tokens = self.token_limit

        rm = []

        for m in reversed(messages or self.messages):

            if 'tool_calls' in m and elide_args:
                m = deepcopy(m)
                for tc in m['tool_calls']:
                    tc['function']['arguments'] = '<arguments elided>'
                if 'function_call' in m:
                    del m['function_call']

            toks = len(self.tokenizer.encode(json.dumps(m)))

            if toks < max_tokens:
                max_tokens -= toks
                rm.insert(0, m)
            else:
                break

        # Remote gets cranky if you have a tool call response with
        # no tool calls, so remove it if it is there
        if 'tool_call_id' in rm[0]:
            rm = rm[1:]

        return [self.system] + rm

    def stop(self):
        pass

    def print_content_cb(self, chunk):
        # clear_output(wait=True)

        content = chunk.choices[0].delta.content

        if content is not None:
            print(content, end='')

    def process_streamed_response(self, g, call_back=None):
        """Read the streamed responses from a call to the chat completions interface, and call the callback
        for each chunk. Returns all of the chunks aggregated into one chunk, and a list of each response """
        from copy import deepcopy

        chunk = None
        responses = []

        for r in g:

            if call_back is not None:
                call_back(r)

            responses.append(r)

            if chunk is None:
                chunk = deepcopy(r)
            else:
                # Copy over the content changes
                for j, (chunk_choice, r_choice) in enumerate(zip(chunk.choices, r.choices)):
                    if chunk_choice.delta.content is None:
                        chunk_choice.delta.content = r_choice.delta.content or ''
                    else:
                        chunk_choice.delta.content += r_choice.delta.content or ''

                    # Then the tool calls
                    if r_choice.delta.tool_calls:
                        if not chunk_choice.delta.tool_calls:
                            chunk_choice.delta.tool_calls = r_choice.delta.tool_calls
                        else:

                            for (chunk_tc, r_tc) in zip(chunk_choice.delta.tool_calls, r_choice.delta.tool_calls):
                                chunk_tc.function.arguments += r_tc.function.arguments

                    # Copy the finish reason. We are assigning this, not appending it, because we really only
                    # want thte last one
                    chunk_choice.finish_reason = r_choice.finish_reason

        return chunk, responses

    def run(self, prompt: str | List[dict[str, Any]], streaming=True, **kwargs) -> str:
        """Run a  completion request loop"""

        if isinstance(prompt, str):
            self.messages.append({"role": "user", "content": prompt})
        else:
            self.messages.extend(prompt)

        for iteration in count():

            self.iter_key = lambda v: f"/loop/{v}/{iteration:03d}"

            g = self.client.chat.completions.create(
                messages=self.request_messages(),
                tools=self.tools.specification(),
                model=self.model,
                stream=True,
                timeout=10
            )

            chunk, responses = self.process_streamed_response(g, call_back=self.print_content_cb)

            # Clean up the content response so that it is just the content, not any tool calls or other
            # stuff
            self.messages.append({'role': 'assistant', 'content': chunk.choices[0].delta.content})

            self.responses.append(responses)
            self.chunks.append(chunk)

            # Save these to the cache for later analysis or debugging
            self.session_cache['messages'] = self.messages
            self.session_cache['responses'] = self.responses
            self.session_cache['chunks'] = self.chunks

            finish_reason = chunk.choices[0].finish_reason

            match finish_reason:
                case "stop" | "content_filter":
                    self.stop()
                    return self.last_content
                case "length":
                    self.stop()
                    return self.last_content
                case "function_call" | "tool_calls":
                    try:
                        messages = self.call_function(chunk)
                        self.messages.extend(messages)
                    except Done:
                        self.stop()
                        return self.last_content

                case "null":
                    pass  # IDK what to do here.

                case _:
                    logger.debug(f"Unknown finish reason: {finish_reason}")

        return finish_reason

    def count_tokens(self, r):

        if not isinstance(r, str):
            r = json.dumps(r, indent=2)

        return len(self.tokenizer.encode(r))

    def call_function(self, chunk):
        """Call a function references in the response, the add the function result to the messages"""

        delta = chunk.choices[0].delta

        m = delta.model_dump()
        m['content'] = ''

        messages = [m]

        for tool_call in delta.tool_calls:

            m = {
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": tool_call.function.name,
                "content": None
            }

            try:
                self.display(f"Calling tool '{tool_call.function.name}'")
                r = self.tools.run_tool(tool_call.function.name, tool_call.function.arguments)

                if not isinstance(r, str):
                    r = json.dumps(r, indent=2)

                toks = self.count_tokens(r)

                if toks > self.token_limit / 2:
                    max_preview = int(len(r) / toks * (self.token_limit / 4))

                    r = 'ERROR: Response too long to return to model. Try to make it smaller. ' + \
                        'Here is the first part of the response: \n\n' + r[:max_preview]

                m['content'] = r
                messages.append(m)

            except Exception as e:
                e_msg = f"Failed to call tool '{tool_call.function.name}' with args '{tool_call.function.arguments}': {e} "
                logger.error(e_msg)
                m['content'] = str(e_msg)
                messages.append(m)

        return messages


class MyTestCase(unittest.TestCase):
    def test_basic(self):
        import typesense
        from pathlib import Path

        logging.basicConfig()
        logger.setLevel(logging.DEBUG)

        # rc = ObjectStore.new(bucket='test', class_='FSObjectStore', path='/tmp/cache')

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
