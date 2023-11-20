import inspect
from typing import Any, Dict, List, Type, get_type_hints

from docstring_parser import parse
from termcolor import colored

from pydantic import BaseModel


def map_types(v):
    return {
        "str": "string",
        "int": "integer",
        "Any": "object",
        "list": "object",
        "Optional": "object",
    }.get(v, v)


def get_pydantic_model_spec(model: Type[BaseModel]) -> Dict[str, Any]:
    """Generate specification for Pydantic model fields."""
    spec = {}
    for field_name, field in model.model_fields.items():
        spec[field_name] = {
            "type": map_types(field.annotation.__name__),
            "description": field.description,
        }
    return spec


def generate_tools_specification(cls: Type) -> List[Dict[str, Any]]:
    """
    Generates a tools specification from a class's methods, annotations, and docstrings
    using the docstring_parser module. It excludes the 'self' parameter from methods.
    """
    functions_spec = []

    for name, method in inspect.getmembers(cls, inspect.isfunction):
        if name.startswith("__"):
            continue

        sig = inspect.signature(method)
        docstring = method.__doc__
        parsed_docstring = parse(docstring) if docstring else None

        function_spec = {
            "name": name,
            "description": parsed_docstring.short_description
            if parsed_docstring
            else "",
            "parameters": {"type": "object", "properties": {}},
            "result": {
                "type": "object",
                "description": parsed_docstring.returns.description
                if parsed_docstring and parsed_docstring.returns
                else "",
                "properties": {},
            },
        }

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue  # Skip the 'self' parameter

            param_type = param.annotation
            if param_type == param.empty:
                param_type = Any
            else:
                param_type = get_type_hints(method)[param_name]

            param_doc = (
                next(
                    (p for p in parsed_docstring.params if p.arg_name == param_name),
                    None,
                )
                if parsed_docstring
                else None
            )
            param_description = param_doc.description if param_doc else ""

            if inspect.isclass(param_type) and issubclass(param_type, BaseModel):
                function_spec["parameters"]["properties"][param_name] = {
                    "type": map_types(param_type.__name__),
                    "description": param_description,
                    "properties": get_pydantic_model_spec(param_type),
                }
            else:
                function_spec["parameters"]["properties"][param_name] = {
                    "type": map_types(param_type.__name__),
                    "description": param_description,
                }

        return_type = sig.return_annotation
        if return_type == sig.empty:
            return_type = Any
        else:
            return_type = get_type_hints(method).get("return", Any)

        if inspect.isclass(return_type) and issubclass(return_type, BaseModel):
            function_spec["result"] = {
                "type": return_type.__name__,
                "properties": get_pydantic_model_spec(return_type),
            }
        else:
            function_spec["result"]["type"] = (
                return_type.__name__
                if not isinstance(return_type, str)
                else return_type
            )

        # Patch up bad formatting
        function_spec = {"type": "function", "function": function_spec}

        functions_spec.append(function_spec)

    return functions_spec


def pretty_print_conversation(messages):
    role_to_color = {
        "system": "red",
        "user": "green",
        "assistant": "blue",
        "tool": "magenta",
    }

    for message in messages:
        try:
            role = message.get("role", "unknown")
            content = (message.get("content", "no content") or "")[:120]
            tool_call = (message.get("tool_calls", "") or "")[:120]
            name = message.get("name")
        except AttributeError:
            print("BAD!", message)
            continue

        if role == "system":
            print(colored(f"system: {content}\n", role_to_color[role]))
        elif role == "user":
            print(colored(f"user: {content}\n", role_to_color[role]))
        elif role == "assistant" and tool_call:
            print(colored(f"assistant: {tool_call}\n", role_to_color[role]))
        elif role == "assistant" and not tool_call:
            print(colored(f"assistant: {content}\n", role_to_color[role]))
        elif role == "tool":
            print(colored(f"function ({name}): {content}\n", role_to_color[role]))
        else:
            print(colored(f"unknown: {content}\n"))

    # Models list from the OpenAI OpenAPI spec at
    # https://github.com/openai/openai-openapi/blob/master/openapi.yaml


def get_model_list():  # noqa: F841
    """Retrieve the current list of models from the OpenAI OpenAPI spec"""
    import requests
    import yaml

    r = requests.get(
        "https://raw.githubusercontent.com/openai/openai-openapi/master/openapi.yaml"
    )
    spec = yaml.safe_load(r.content.decode("utf-8"))
    models = spec["components"]["schemas"]["CreateChatCompletionRequest"][
        "properties"
    ]["model"]["anyOf"][1]["enum"]
    return models


models = [  # noqa: F841
    "gpt-4-1106-preview",
    "gpt-4-vision-preview",
    "gpt-4",
    "gpt-4-0314",
    "gpt-4-0613",
    "gpt-4-32k",
    "gpt-4-32k-0314",
    "gpt-4-32k-0613",
    "gpt-3.5-turbo-1106",
    "gpt-3.5-turbo",
    "gpt-3.5-turbo-16k",
    "gpt-3.5-turbo-0301",
    "gpt-3.5-turbo-0613",
    "gpt-3.5-turbo-16k-0613",
]

# Costs for models,
# ( prompt cost, completion cost )
# noinspection PyUnusedLocal
costs = {  # noqa: F841
    "gpt-4-1106-preview": (0.0100, 0.0300),
    "gpt-4": (0.0300, 0.0600),
    "gpt-4-32k": (0.0600, 0.1200),
    "gpt-3.5-turbo-16k-0613": (0.0010, 0.0020),
    "gpt-3.5-turbo-1106": (0.0010, 0.0020),
}


def serialize(o: Any):
    """Serialize an object to JSON"""
    import pandas as pd
    import json

    if isinstance(o, (pd.DataFrame, pd.Series)):
        return o.to_json(orient='records')
    else:
        try:
            return json.dumps(o)
        except TypeError:
            return repr(o)
