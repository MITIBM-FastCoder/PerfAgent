"""The OpenHands-style `str_replace_editor` tool: view, create, str_replace, insert, undo_edit.

The tool description is OpenHands' own `TOOL_DESCRIPTION`, copied below from the `openhands-tools`
package (see the comment at DESCRIPTION for the version) 
"""

# The following notice applies to the TOOL_DESCRIPTION text copied from
# OpenHands software-agent-sdk (openhands-tools 1.47.0).
# Source: https://github.com/OpenHands/software-agent-sdk/blob/v1.47.0/LICENSE
#
# MIT License
#
# Copyright (c) 2026 OpenHands contributors
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from __future__ import annotations

import base64
import json
import shlex
from pathlib import Path

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "assets" / "tools" / "file_editor_runtime.py"
CONTAINER_PATH = "/file_editor_runtime.py"

_PARAMETERS = {
    "type": "object",
    "properties": {
        "command": {
            "description": "The commands to run. Allowed options are: `view`, `create`, `str_replace`, `insert`, `undo_edit`.",
            "enum": ["view", "create", "str_replace", "insert", "undo_edit"],
            "type": "string",
        },
        "path": {
            "description": "Absolute path to file or directory, e.g. `/workspace/file.py` or `/workspace`.",
            "type": "string",
        },
        "file_text": {
            "description": "Required parameter of `create` command, with the content of the file to be created.",
            "type": "string",
        },
        "old_str": {
            "description": "Required parameter of `str_replace` command containing the string in `path` to replace.",
            "type": "string",
        },
        "new_str": {
            "description": "Optional parameter of `str_replace` command containing the new string (if not given, no string will be added). Required parameter of `insert` command containing the string to insert.",
            "type": "string",
        },
        "insert_line": {
            "description": "Required parameter of `insert` command. The `new_str` will be inserted AFTER the line `insert_line` of `path`.",
            "type": "integer",
        },
        "view_range": {
            "description": "Optional parameter of `view` command when `path` points to a file. If none is given, the full file is shown. If provided, the file will be shown in the indicated line number range, e.g. [11, 12] will show lines 11 and 12. Indexing at 1 to start. Setting `[start_line, -1]` shows all lines from `start_line` to the end of the file.",
            "items": {"type": "integer"},
            "type": "array",
        },
    },
    "required": ["command", "path"],
}


# Verbatim copy of openhands.tools.file_editor.definition.TOOL_DESCRIPTION from openhands-tools 1.47.0
# (https://github.com/OpenHands/software-agent-sdk). Update it by pasting the constant from a newer
# release; the argument schema below is kept in sync with FileEditorAction by hand.
DESCRIPTION = """Custom editing tool for viewing, creating and editing files in plain-text format
* State is persistent across command calls and discussions with the user
* If `path` is a text file, `view` displays the result of applying `cat -n`. If `path` is a directory, `view` lists non-hidden files and directories up to 2 levels deep
* The `create` command cannot be used if the specified `path` already exists as a file
* If a `command` generates a long output, it will be truncated and marked with `<response clipped>`
* The `undo_edit` command will revert the last edit made to the file at `path`
* This tool can be used for creating and editing files in plain-text format.


Before using this tool:
1. Use the view tool to understand the file's contents and context
2. Verify the directory path is correct (only applicable when creating new files):
   - Use the view tool to verify the parent directory exists and is the correct location

When making edits:
   - Ensure the edit results in idiomatic, correct code
   - Do not leave the code in a broken state
   - Always use absolute file paths (starting with /)

CRITICAL REQUIREMENTS FOR USING THIS TOOL:

1. EXACT MATCHING: The `old_str` parameter must match EXACTLY one or more consecutive lines from the file, including all whitespace and indentation. The tool will fail if `old_str` matches multiple locations or doesn't match exactly with the file content.

2. UNIQUENESS: The `old_str` must uniquely identify a single instance in the file:
   - Include sufficient context before and after the change point (3-5 lines recommended)
   - If not unique, the replacement will not be performed

3. REPLACEMENT: The `new_str` parameter should contain the edited lines that replace the `old_str`. Both strings must be different.

Remember: when making multiple file edits in a row to the same file, you should prefer to send all edits in a single message with multiple calls to this tool, rather than multiple messages with a single call each.
"""

SCHEMA = {
    "type": "function",
    "function": {"name": "str_replace_editor", "description": DESCRIPTION, "parameters": _PARAMETERS},
}


# Keys of the runtime's JSON result that are kept in the observation's `extra` (trajectory only,
# never shown to the model), under the names the paper's trajectories used.
_EXTRA_FIELDS = {
    "editor_command": "command",
    "editor_path": "path",
    "prev_exist": "prev_exist",
    "old_content": "old_content",
    "new_content": "new_content",
}


def _last_json_line(output: str) -> dict | None:
    for line in reversed(output.splitlines()):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        return payload if isinstance(payload, dict) else None
    return None


class StrReplaceEditorTool:
    name = "str_replace_editor"
    schema = SCHEMA

    def __init__(self, runtime_path: str = CONTAINER_PATH):
        self.runtime_path = runtime_path

    def deploy(self, env) -> None:
        """Write the runtime into an environment that `workspace.materialize` did not set up.

        Used by tests and local runs; task containers get the file at materialize time.
        """
        source = RUNTIME_SRC.read_text(encoding="utf-8")
        command = f"cat > {shlex.quote(self.runtime_path)} <<'PERFAGENT_EDITOR_EOF'\n{source}\nPERFAGENT_EDITOR_EOF\n"
        result = env.execute({"command": command})
        if result.get("returncode", 1) != 0:
            details = result.get("exception_info") or result.get("output", "").strip() or "unknown error"
            raise RuntimeError(f"could not write the editor runtime to {self.runtime_path}: {details}")

    def command(self, args: dict, *, namespace: str) -> str:
        """The bash command for one editor call. The arguments travel base64-encoded, so no quoting
        of file contents is involved; `namespace` keeps one agent's undo history apart from another's."""
        payload = {**args, "_history_namespace": namespace}
        encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
        return (
            'PYTHON_BIN=python3; command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN=python; '
            f'"$PYTHON_BIN" {shlex.quote(self.runtime_path)} {shlex.quote(encoded)}'
        )

    def execute(self, env, args: dict, *, namespace: str) -> dict:
        """Run one editor call and return an output dict shaped like a bash action's."""
        result = env.execute({"command": self.command(args, namespace=namespace)})
        payload = _last_json_line(result.get("output", ""))
        if payload is None or "ok" not in payload or "text" not in payload:
            # The runtime did not run at all (file missing, no python): show the raw failure.
            return result
        return {
            "output": payload["text"],
            "returncode": 0 if payload.get("ok") else 1,
            "exception_info": result.get("exception_info", ""),
            "extra": {key: payload.get(src) for key, src in _EXTRA_FIELDS.items()},
        }
