"""Build the framework agent while preserving the original JSON tool schemas."""

import json
import logging
from math import isfinite
from langchain.agents import create_agent
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from data_loader import DataValidationError
from tool_schemas import TOOLS, TOOL_FUNCTIONS
from order_selection import remember_selection
from plan_context import remember_plan
from skills import PROMPT_VERSION, SYSTEM_PROMPT  # noqa: F401  (re-exported)

logger = logging.getLogger(__name__)

# The agent's instructions are composed from the static Skill files (skills.py).



def _validate_arguments(value, schema, path="arguments"):
    """Validate the JSON Schema subset used by this project's tools."""
    kind = schema["type"]
    valid = {
        "object": isinstance(value, dict), "array": isinstance(value, list),
        "string": isinstance(value, str), "integer": type(value) is int,
        "number": type(value) in (int, float), "boolean": type(value) is bool,
    }
    if not valid.get(kind, False):
        raise ValueError(f"{path} must be {kind}.")
    if kind == "object":
        properties = schema.get("properties", {})
        missing = set(schema.get("required", [])) - set(value)
        if missing:
            raise ValueError(f"{path} is missing: {', '.join(sorted(missing))}.")
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            raise ValueError(f"{path} contains unsupported parameters.")
        return {key: _validate_arguments(item, properties[key], f"{path}.{key}")
                for key, item in value.items()}
    if kind == "array":
        return [_validate_arguments(item, schema["items"], f"{path}[{index}]")
                for index, item in enumerate(value)]
    if kind == "string":
        value = value.strip()
        if not value:
            raise ValueError(f"{path} cannot be empty.")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path} must be one of {schema['enum']}.")
    if kind in ("integer", "number"):
        if not isfinite(value):
            raise ValueError(f"{path} must be finite.")
        if "minimum" in schema and value < schema["minimum"]:
            raise ValueError(f"{path} must be at least {schema['minimum']}.")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValueError(f"{path} must be at most {schema['maximum']}.")
    return value


def execute_tool(name, arguments):
    """Use the original tool schema for both model guidance and validation."""
    if name not in TOOL_FUNCTIONS:
        return {"status": "error", "message": "Unsupported tool."}
    schema = next(tool["function"]["parameters"] for tool in TOOLS
                  if tool["function"]["name"] == name)
    try:
        params = _validate_arguments(json.loads(arguments), schema)
    except (ValueError, TypeError) as exc:
        return {"status": "error", "message": f"Invalid tool arguments: {exc}"}
    try:
        result = TOOL_FUNCTIONS[name](**params)
        remember_selection(name, result)
        remember_plan(name, result)
        return result
    except DataValidationError as exc:
        return {"status": "error", "message": str(exc)}
    except OSError:
        logger.exception("Tool %s could not read the factory data", name)
        return {"status": "error", "message": "Could not read the factory data."}
    except (ValueError, TypeError, OverflowError) as exc:
        return {"status": "error", "message": f"Invalid tool arguments or data: {exc}"}
    except Exception:
        # A bug in the tool, not a data problem: keep the traceback and say so plainly.
        logger.exception("Tool %s failed", name)
        return {"status": "error", "message": "Internal tool error: this lookup did not run. "
                                              "Tell the user it failed; do not guess an answer."}



def build_tools():
    """Pass JSON schemas unchanged; validate arguments in the shared executor."""
    wrapped = []
    def bind(name):
        def run_tool(**kwargs):
            return json.dumps(execute_tool(name, json.dumps(kwargs)), ensure_ascii=False)
        return run_tool
    for spec in TOOLS:
        info = spec["function"]
        wrapped.append(StructuredTool(name=info["name"], description=info["description"],
                                      args_schema=info["parameters"], func=bind(info["name"])))
    return wrapped


def build_agent(config):
    """Create one LangChain agent, powered by LangGraph's execution loop."""
    if not config.api_key:
        raise ValueError("Missing API key.")
    options = dict(model=config.model, api_key=config.api_key, base_url=config.base_url,
                   timeout=60, max_retries=1, model_kwargs={'parallel_tool_calls': False})
    if config.provider == "deepseek":
        options.update(max_tokens=2048, extra_body={"thinking": {"type": "disabled"}})
    else:
        options["max_completion_tokens"] = 4096
    return create_agent(ChatOpenAI(**options), tools=build_tools(), system_prompt=SYSTEM_PROMPT)
