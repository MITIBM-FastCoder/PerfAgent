"""Litellm model wrapper used by PerfAgent."""

import litellm
from minisweagent.models.litellm_model import LitellmModel, LitellmModelConfig

from perfagent.tools import get_tools, parse_toolcall_actions


class PerfLitellmModelConfig(LitellmModelConfig):
    extra_tools: list[str] = []
    """Tools offered to the model besides bash, by name (e.g. ["str_replace_editor"]). See perfagent.tools."""


class PerfLitellmModel(LitellmModel):
    def __init__(self, *, config_class: type = PerfLitellmModelConfig, **kwargs):
        super().__init__(config_class=config_class, **kwargs)
        get_tools(self.config.extra_tools)  # reject unknown tool names at startup, not at the first query
        self._text_only_query = False

    def _query(self, messages: list[dict[str, str]], **kwargs):
        try:
            merged = {"tools": get_tools(self.config.extra_tools)} | self.config.model_kwargs | kwargs
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
        return parse_toolcall_actions(
            response.choices[0].message.tool_calls or [],
            format_error_template=self.config.format_error_template,
            template_kwargs={"finish_reason": response.choices[0].finish_reason},
            extra_tools=self.config.extra_tools,
        )
