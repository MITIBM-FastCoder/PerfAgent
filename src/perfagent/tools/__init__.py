"""Tools the model can call besides bash.

mini-swe-agent offers the model one `bash` tool and its parser rejects any other name. This
package keeps a registry of extra tools. Each one has an OpenAI-style function schema and executes
through the environment's `execute`, so it needs nothing that bash actions do not already have.
`PerfLitellmModel` offers the tools named in its `extra_tools` config and parses their calls into
actions carrying `tool` and `args`; `PerfAgent._execute_action` dispatches those by name. Bash
actions keep the stock shape (`command` and `tool_call_id`, no `tool` key).
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from jinja2 import StrictUndefined, Template
from minisweagent.exceptions import FormatError
from minisweagent.models.utils.actions_toolcall import BASH_TOOL

from perfagent.tools.str_replace_editor import StrReplaceEditorTool

EXTRA_TOOLS = {StrReplaceEditorTool.name: StrReplaceEditorTool()}
"""Every extra tool the harness knows, by name. A config enables a subset with `model.extra_tools`."""


def get_tool(name: str):
    return EXTRA_TOOLS.get(name)


def get_tools(extra_tools: Iterable[str] = ()) -> list[dict]:
    """The schemas handed to the API: bash plus the enabled extra tools, in that order."""
    tools = [BASH_TOOL]
    for name in extra_tools:
        if name not in EXTRA_TOOLS:
            raise ValueError(f"unknown extra tool {name!r}; available: {sorted(EXTRA_TOOLS)}")
        tools.append(EXTRA_TOOLS[name].schema)
    return tools


def _format_error(template: str, error: str, **kwargs) -> FormatError:
    return FormatError(
        {
            "role": "user",
            "content": Template(template, undefined=StrictUndefined).render(error=error, actions=[], **kwargs),
            "extra": {"interrupt_type": "FormatError"},
        }
    )


def parse_toolcall_actions(
    tool_calls: list,
    *,
    format_error_template: str,
    template_kwargs: dict | None = None,
    extra_tools: Iterable[str] = (),
) -> list[dict]:
    """mini-swe-agent's tool-call parser, extended to the enabled extra tools.

    Same errors as upstream (no tool calls, bad JSON, unknown tool, bash without `command`), the
    same template variables (`has_tool_calls` plus `template_kwargs`), and the same action shape
    for bash. A call to an enabled extra tool becomes `{"tool", "args", "tool_call_id"}`; its
    arguments are checked by the tool itself when it runs, which gives the model a precise message.
    """
    template_kwargs = template_kwargs or {}
    enabled = set(extra_tools)
    if not tool_calls:
        raise _format_error(
            format_error_template,
            "No tool calls found in the response. Every response MUST include at least one tool call.",
            has_tool_calls=False,
            **template_kwargs,
        )
    actions = []
    for tool_call in tool_calls:
        error_msg = ""
        args: object = {}
        name = tool_call.function.name
        try:
            args = json.loads(tool_call.function.arguments)
        except Exception as e:
            error_msg = f"Error parsing tool call arguments: {e}."
        if name != "bash" and name not in enabled:
            error_msg += f"Unknown tool '{name}'."
        elif not isinstance(args, dict):
            error_msg += f"Arguments of tool '{name}' must be a JSON object."
        elif name == "bash" and "command" not in args:
            error_msg += "Missing 'command' argument in bash tool call."
        if error_msg:
            raise _format_error(format_error_template, error_msg.strip(), has_tool_calls=True, **template_kwargs)
        if name == "bash":
            actions.append({"command": args["command"], "tool_call_id": tool_call.id})
        else:
            actions.append({"tool": name, "args": args, "tool_call_id": tool_call.id})
    return actions
