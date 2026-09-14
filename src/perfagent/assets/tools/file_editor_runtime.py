#!/usr/bin/env python3
"""Vendored file editor runtime executed inside the target environment.

This is a stdlib-only compatibility runtime inspired by the OpenHands
FileEditor implementation. It intentionally avoids third-party dependencies so
it can run inside older benchmark images while preserving the important
behavioral guarantees of the upstream tool.
"""

import base64
import json
import locale
import os
import re
import sys


MAX_RESPONSE_LEN_CHAR = 16000
TEXT_FILE_CONTENT_TRUNCATED_NOTICE = (
    "<response clipped><NOTE>Due to the max output limit, only part of this file "
    "has been shown to you. You should retry this tool after you have searched "
    "inside the file with `grep -n` in order to find the line numbers of what "
    "you are looking for.</NOTE>"
)
BINARY_FILE_CONTENT_TRUNCATED_NOTICE = (
    "<response clipped><NOTE>Due to the max output limit, only part of this file "
    "has been shown to you. Please use Python libraries to view the entire file "
    "or search for specific content within the file.</NOTE>"
)
DIRECTORY_CONTENT_TRUNCATED_NOTICE = (
    "<response clipped><NOTE>Due to the max output limit, only part of this "
    "directory has been shown to you. You should use `ls -la` instead to view "
    "large directories incrementally.</NOTE>"
)
SNIPPET_CONTEXT_WINDOW = 4
MAX_FILE_SIZE_MB = 10
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


class ToolError(Exception):
    def __init__(self, message):
        self.message = message
        Exception.__init__(self, message)


class EditorToolParameterMissingError(ToolError):
    def __init__(self, command, parameter):
        ToolError.__init__(
            self,
            "Parameter `{}` is required for command: {}.".format(parameter, command),
        )


class EditorToolParameterInvalidError(ToolError):
    def __init__(self, parameter, value, hint=None):
        if hint:
            message = "Invalid `{}` parameter: {}. {}".format(parameter, value, hint)
        else:
            message = "Invalid `{}` parameter: {}.".format(parameter, value)
        ToolError.__init__(self, message)


class FileValidationError(ToolError):
    def __init__(self, path, reason):
        ToolError.__init__(
            self,
            "File validation failed for {}: {}".format(path, reason),
        )


def _print_result(payload):
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    sys.stdout.write("\n")


def _success(text, command, path=None, prev_exist=True, old_content=None, new_content=None):
    _print_result(
        {
            "ok": True,
            "text": text,
            "command": command,
            "path": path,
            "prev_exist": prev_exist,
            "old_content": old_content,
            "new_content": new_content,
        }
    )


def _error(message, command=None, path=None):
    _print_result(
        {
            "ok": False,
            "text": message,
            "command": command,
            "path": path,
            "prev_exist": True,
            "old_content": None,
            "new_content": None,
        }
    )


def _maybe_truncate(content, truncate_notice):
    if len(content) <= MAX_RESPONSE_LEN_CHAR:
        return content
    available = MAX_RESPONSE_LEN_CHAR - len(truncate_notice)
    if available <= 0:
        return truncate_notice[:MAX_RESPONSE_LEN_CHAR]
    return content[:available] + truncate_notice


def _make_output(content, description, start_line=1, truncate_notice=TEXT_FILE_CONTENT_TRUNCATED_NOTICE):
    snippet = _maybe_truncate(content, truncate_notice)
    numbered = "\n".join(
        "%6d\t%s" % (i + start_line, line)
        for i, line in enumerate(snippet.split("\n"))
    )
    return "Here's the result of running `cat -n` on {}:\n{}\n".format(description, numbered)


def _history_root(namespace):
    return os.path.join("/tmp", "_mswea_editor_history", namespace)


def _history_paths(path, namespace):
    abs_path = os.path.abspath(path)
    key = base64.urlsafe_b64encode(abs_path.encode("utf-8")).decode("ascii")
    root = _history_root(namespace)
    return (
        os.path.join(root, key + ".metadata.json"),
        os.path.join(root, key + ".entries"),
    )


def _ensure_parent(path):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _load_metadata(metadata_path):
    if not os.path.exists(metadata_path):
        return {"entries": [], "counter": 0}
    try:
        with open(metadata_path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return {"entries": [], "counter": 0}


def _save_metadata(metadata_path, metadata):
    _ensure_parent(metadata_path)
    with open(metadata_path, "w", encoding="utf-8") as handle:
        json.dump(metadata, handle)


def _history_entry_path(entries_dir, counter):
    return os.path.join(entries_dir, "{}.txt".format(counter))


def _add_history(path, content, namespace, max_entries=10):
    metadata_path, entries_dir = _history_paths(path, namespace)
    metadata = _load_metadata(metadata_path)
    counter = metadata.get("counter", 0)
    os.makedirs(entries_dir, exist_ok=True)
    with open(_history_entry_path(entries_dir, counter), "w", encoding="utf-8") as handle:
        handle.write(content)
    metadata["entries"].append(counter)
    metadata["counter"] = counter + 1
    while len(metadata["entries"]) > max_entries:
        old_counter = metadata["entries"].pop(0)
        old_path = _history_entry_path(entries_dir, old_counter)
        if os.path.exists(old_path):
            os.remove(old_path)
    _save_metadata(metadata_path, metadata)


def _pop_history(path, namespace):
    metadata_path, entries_dir = _history_paths(path, namespace)
    metadata = _load_metadata(metadata_path)
    entries = metadata.get("entries", [])
    if not entries:
        return None
    counter = entries.pop()
    entry_path = _history_entry_path(entries_dir, counter)
    content = None
    if os.path.exists(entry_path):
        with open(entry_path, "r", encoding="utf-8") as handle:
            content = handle.read()
        os.remove(entry_path)
    metadata["entries"] = entries
    _save_metadata(metadata_path, metadata)
    return content


def _detect_encoding(path):
    sample_size = min(os.path.getsize(path), 1024 * 1024)
    with open(path, "rb") as handle:
        sample = handle.read(sample_size)
    if b"\x00" in sample:
        raise FileValidationError(
            path,
            "File appears to be binary and this file type cannot be read or edited by this tool.",
        )
    candidates = []
    preferred = locale.getpreferredencoding(False) or "utf-8"
    for encoding in ("utf-8", "utf-8-sig", preferred, "latin-1"):
        if encoding not in candidates:
            candidates.append(encoding)
    for encoding in candidates:
        try:
            sample.decode(encoding)
            return "utf-8" if encoding.lower() == "ascii" else encoding
        except Exception:
            continue
    raise FileValidationError(
        path,
        "File appears to be binary and this file type cannot be read or edited by this tool.",
    )


def _validate_file(path):
    if not os.path.exists(path) or not os.path.isfile(path):
        return
    file_size = os.path.getsize(path)
    max_size = MAX_FILE_SIZE_MB * 1024 * 1024
    if file_size > max_size:
        raise FileValidationError(
            path,
            "File is too large ({:.1f}MB). Maximum allowed size is {}MB.".format(
                float(file_size) / 1024.0 / 1024.0,
                MAX_FILE_SIZE_MB,
            ),
        )
    extension = os.path.splitext(path)[1].lower()
    if extension in IMAGE_EXTENSIONS:
        return
    _detect_encoding(path)


def _read_file(path, start_line=None, end_line=None):
    _validate_file(path)
    encoding = _detect_encoding(path)
    try:
        with open(path, "r", encoding=encoding) as handle:
            if start_line is None and end_line is None:
                return handle.read(), encoding
            lines = []
            for index, line in enumerate(handle, 1):
                if index > end_line:
                    break
                if index >= start_line:
                    lines.append(line)
            return "".join(lines), encoding
    except UnicodeDecodeError as exc:
        raise ToolError(
            "Cannot view {}: file contains binary content that cannot be decoded as text. Error: {}".format(
                path, exc
            )
        )
    except Exception as exc:
        raise ToolError("Ran into {} while trying to read {}".format(exc, path))


def _write_file(path, file_text, encoding):
    _validate_file(path)
    try:
        with open(path, "w", encoding=encoding) as handle:
            handle.write(file_text)
    except Exception as exc:
        raise ToolError("Ran into {} while trying to write to {}".format(exc, path))


def _count_lines(path):
    _validate_file(path)
    encoding = _detect_encoding(path)
    with open(path, "r", encoding=encoding) as handle:
        return sum(1 for _ in handle)


def _validate_path(command, path, workspace_root):
    if not os.path.isabs(path):
        suggestion = "The path should be an absolute path, starting with `/`."
        suggested_path = os.path.abspath(os.path.join(workspace_root, path))
        if os.path.exists(suggested_path):
            suggestion += " Maybe you meant {}?".format(suggested_path)
        raise EditorToolParameterInvalidError("path", path, suggestion)

    if command == "create" and os.path.exists(path):
        raise EditorToolParameterInvalidError(
            "path",
            path,
            "File already exists at: {}. Cannot overwrite files using command `create`.".format(path),
        )
    if command != "create" and not os.path.exists(path):
        raise EditorToolParameterInvalidError(
            "path",
            path,
            "The path {} does not exist. Please provide a valid path.".format(path),
        )
    if command != "view" and os.path.isdir(path):
        raise EditorToolParameterInvalidError(
            "path",
            path,
            "The path {} is a directory and only the `view` command can be used on directories.".format(path),
        )


def _list_directory(path):
    hidden_count = 0
    try:
        for entry in os.listdir(path):
            if entry.startswith("."):
                hidden_count += 1
    except Exception as exc:
        raise ToolError(str(exc))

    entries = []
    for root, dirs, files in os.walk(path, topdown=True, followlinks=True):
        rel = os.path.relpath(root, path)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if depth >= 2:
            dirs[:] = []
            continue
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for directory in dirs:
            entries.append(os.path.join(root, directory) + "/")
        for filename in sorted(files):
            if not filename.startswith("."):
                entries.append(os.path.join(root, filename))

    message = "Here's the files and directories up to 2 levels deep in {}, excluding hidden items:\n{}".format(
        path,
        "\n".join(sorted(entries)),
    )
    if hidden_count > 0:
        message += "\n\n{} hidden files/directories in this directory are excluded. You can use 'ls -la {}' to see them.".format(
            hidden_count, path
        )
    return _maybe_truncate(message, DIRECTORY_CONTENT_TRUNCATED_NOTICE)


def _view(path, view_range):
    if os.path.isdir(path):
        if view_range:
            raise EditorToolParameterInvalidError(
                "view_range",
                str(view_range),
                "The `view_range` parameter is not allowed when `path` points to a directory.",
            )
        return _list_directory(path)

    _validate_file(path)
    num_lines = _count_lines(path)
    if not view_range:
        file_content, _ = _read_file(path)
        return _make_output(file_content, path)

    if (
        not isinstance(view_range, list)
        or len(view_range) != 2
        or not all(isinstance(item, int) for item in view_range)
    ):
        raise EditorToolParameterInvalidError(
            "view_range",
            str(view_range),
            "It should be a list of two integers.",
        )

    start_line, end_line = view_range
    if start_line < 1 or start_line > num_lines:
        raise EditorToolParameterInvalidError(
            "view_range",
            str(view_range),
            "Its first element `{}` should be within the range of lines of the file: {}.".format(
                start_line, [1, num_lines]
            ),
        )
    warning_message = None
    if end_line == -1:
        end_line = num_lines
    elif end_line > num_lines:
        warning_message = "We only show up to {} since there're only {} lines in this file.".format(
            num_lines, num_lines
        )
        end_line = num_lines
    if end_line < start_line:
        raise EditorToolParameterInvalidError(
            "view_range",
            str(view_range),
            "Its second element `{}` should be greater than or equal to the first element `{}`.".format(
                end_line, start_line
            ),
        )
    file_content, _ = _read_file(path, start_line=start_line, end_line=end_line)
    output = _make_output("\n".join(file_content.splitlines()), path, start_line=start_line)
    if warning_message:
        output = "NOTE: {}\n{}".format(warning_message, output)
    return output


def _create(path, file_text):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    encoding = "utf-8"
    with open(path, "w", encoding=encoding) as handle:
        handle.write(file_text)
    return "File created successfully at: {}".format(path)


def _str_replace(path, old_str, new_str, history_namespace):
    _validate_file(path)
    file_content, encoding = _read_file(path)
    new_str = new_str or ""
    occurrences = [
        (
            file_content.count("\n", 0, match.start()) + 1,
            match.group(),
            match.start(),
        )
        for match in re.finditer(re.escape(old_str), file_content)
    ]
    if not occurrences:
        stripped_old = old_str.strip()
        stripped_new = new_str.strip()
        occurrences = [
            (
                file_content.count("\n", 0, match.start()) + 1,
                match.group(),
                match.start(),
            )
            for match in re.finditer(re.escape(stripped_old), file_content)
        ]
        if not occurrences:
            raise ToolError(
                "No replacement was performed, old_str `{}` did not appear verbatim in {}.".format(
                    old_str, path
                )
            )
        old_str = stripped_old
        new_str = stripped_new
    if len(occurrences) > 1:
        line_numbers = sorted(set(line for line, _, _ in occurrences))
        raise ToolError(
            "No replacement was performed. Multiple occurrences of old_str `{}` in lines {}. Please ensure it is unique.".format(
                old_str, line_numbers
            )
        )

    replacement_line, matched_text, index = occurrences[0]
    new_file_content = file_content[:index] + new_str + file_content[index + len(matched_text) :]
    _add_history(path, file_content, history_namespace)
    _write_file(path, new_file_content, encoding)
    start_line = max(0, replacement_line - SNIPPET_CONTEXT_WINDOW)
    end_line = replacement_line + SNIPPET_CONTEXT_WINDOW + new_str.count("\n")
    snippet, _ = _read_file(path, start_line=start_line + 1, end_line=end_line)
    message = "The file {} has been edited. ".format(path)
    message += _make_output(snippet, "a snippet of {}".format(path), start_line=start_line + 1)
    message += "Review the changes and make sure they are as expected. Edit the file again if necessary."
    return message, file_content, new_file_content


def _insert(path, insert_line, new_str, history_namespace):
    _validate_file(path)
    num_lines = _count_lines(path)
    if insert_line < 0 or insert_line > num_lines:
        raise EditorToolParameterInvalidError(
            "insert_line",
            str(insert_line),
            "It should be within the range of allowed values: {}".format([0, num_lines]),
        )
    file_content, encoding = _read_file(path)
    lines = file_content.splitlines(True)
    _add_history(path, file_content, history_namespace)
    new_lines = ["{}\n".format(line) for line in new_str.split("\n")]
    updated_lines = lines[:insert_line] + new_lines + lines[insert_line:]
    new_file_content = "".join(updated_lines)
    _write_file(path, new_file_content, encoding)
    start_line = max(0, insert_line - SNIPPET_CONTEXT_WINDOW)
    end_line = min(
        len(updated_lines),
        insert_line + SNIPPET_CONTEXT_WINDOW + len(new_lines),
    )
    snippet = "".join(updated_lines[start_line:end_line])
    message = "The file {} has been edited. ".format(path)
    message += _make_output(
        snippet,
        "a snippet of the edited file",
        start_line=max(1, insert_line - SNIPPET_CONTEXT_WINDOW + 1),
    )
    message += (
        "Review the changes and make sure they are as expected (correct indentation, "
        "no duplicate lines, etc). Edit the file again if necessary."
    )
    return message, file_content, new_file_content


def _undo_edit(path, history_namespace):
    _validate_file(path)
    current_text, encoding = _read_file(path)
    old_text = _pop_history(path, history_namespace)
    if old_text is None:
        raise ToolError("No edit history found for {}.".format(path))
    _write_file(path, old_text, encoding)
    message = "Last edit to {} undone successfully. {}".format(
        path,
        _make_output(old_text, path),
    )
    return message, current_text, old_text


def _run(payload):
    command = payload.get("command")
    path = payload.get("path")
    history_namespace = payload.get("_history_namespace", "default")
    workspace_root = os.getcwd()

    if command not in ("view", "create", "str_replace", "insert", "undo_edit"):
        raise ToolError(
            "Unrecognized command {}. The allowed commands for FileEditor tool are: view, create, str_replace, insert, undo_edit".format(
                command
            )
        )

    _validate_path(command, path, workspace_root)

    if command == "view":
        text = _view(path, payload.get("view_range"))
        return {"text": text, "prev_exist": True, "old_content": None, "new_content": None}

    if command == "create":
        if payload.get("file_text") is None:
            raise EditorToolParameterMissingError(command, "file_text")
        text = _create(path, payload.get("file_text"))
        return {
            "text": text,
            "prev_exist": False,
            "old_content": None,
            "new_content": payload.get("file_text"),
        }

    if command == "str_replace":
        if payload.get("old_str") is None:
            raise EditorToolParameterMissingError(command, "old_str")
        if payload.get("new_str") is None:
            raise EditorToolParameterMissingError(command, "new_str")
        if payload.get("old_str") == payload.get("new_str"):
            raise EditorToolParameterInvalidError(
                "new_str",
                payload.get("new_str"),
                "No replacement was performed. `new_str` and `old_str` must be different.",
            )
        text, old_content, new_content = _str_replace(
            path,
            payload.get("old_str"),
            payload.get("new_str"),
            history_namespace,
        )
        return {
            "text": text,
            "prev_exist": True,
            "old_content": old_content,
            "new_content": new_content,
        }

    if command == "insert":
        if payload.get("insert_line") is None:
            raise EditorToolParameterMissingError(command, "insert_line")
        if payload.get("new_str") is None:
            raise EditorToolParameterMissingError(command, "new_str")
        text, old_content, new_content = _insert(
            path,
            payload.get("insert_line"),
            payload.get("new_str"),
            history_namespace,
        )
        return {
            "text": text,
            "prev_exist": True,
            "old_content": old_content,
            "new_content": new_content,
        }

    text, old_content, new_content = _undo_edit(path, history_namespace)
    return {
        "text": text,
        "prev_exist": True,
        "old_content": old_content,
        "new_content": new_content,
    }


def main():
    command = None
    path = None
    try:
        payload = json.loads(base64.b64decode(sys.argv[1]).decode("utf-8"))
        command = payload.get("command")
        path = payload.get("path")
        result = _run(payload)
        _success(
            result["text"],
            command,
            path=path,
            prev_exist=result.get("prev_exist", True),
            old_content=result.get("old_content"),
            new_content=result.get("new_content"),
        )
    except ToolError as exc:
        _error(exc.message, command=command, path=path)
    except Exception as exc:
        _error("Unexpected editor runtime error: {}".format(exc), command=command, path=path)


if __name__ == "__main__":
    main()
