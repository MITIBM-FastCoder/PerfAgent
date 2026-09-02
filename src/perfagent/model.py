"""Litellm model wrapper used by PerfAgent."""

import litellm

from minisweagent.models.litellm_model import LitellmModel
from minisweagent.models.utils.actions_toolcall import BASH_TOOL


class PerfLitellmModel(LitellmModel):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._text_only_query = False

    def _query(self, messages: list[dict[str, str]], **kwargs):
        try:
            merged = {"tools": [BASH_TOOL]} | self.config.model_kwargs | kwargs
            # A pure-text query (tools=[]) must not also request/force a tool call:
            # tool_choice set to `required` with no tools is rejected by the OpenAI API.
            if not merged.get("tools"):
                merged.pop("tool_choice", None)
            return litellm.completion(
                model=self.config.model_name,
                messages=messages,
                **merged,
            )
        except litellm.exceptions.AuthenticationError as e:
            e.message += " You can permanently set your API key with `mini-extra config set KEY VALUE`."
            raise

    def query(self, messages: list[dict[str, str]], **kwargs) -> dict:
        # tools=[] marks a pure text-completion query (profiler summaries):
        # no tool call is expected, so _parse_actions must not raise FormatError.
        self._text_only_query = kwargs.get("tools") == []
        try:
            return super().query(messages, **kwargs)
        finally:
            self._text_only_query = False

    def _parse_actions(self, response) -> list[dict]:
        if self._text_only_query:
            return []
        return super()._parse_actions(response)
