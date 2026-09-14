"""Agent for performance optimization, based on mini-swe-agent"""

import re
import uuid
from dataclasses import asdict, dataclass

import litellm
from jinja2 import StrictUndefined, Template

from minisweagent import Environment, Model
from minisweagent.agents.default import AgentConfig, DefaultAgent
from minisweagent.exceptions import FormatError, InterruptAgentFlow, LimitsExceeded, Submitted

from perfagent.tools import get_tool

# Record each successful agent attempt, which is outputted after the agent finishes.
@dataclass
class OptAttempt:
    runtime: float
    speedup: float
    perf_report: str
    diff: str


class PerfAgentConfig(AgentConfig):
    """Configuration for the profiling agent. Extends Mini-SWE-Agent's AgentConfig."""

    format_error_template: str
    """Template for format error messages when action parsing fails."""
    action_observation_template: str
    """Template for rendering action observations."""
    runtime_error_template: str
    """Template for build/test/profiler runtime error messages."""
    test_script_perf_template: str
    """Template for performance test results with speedup metrics."""
    perf_summary_template: str
    """Template for requesting profiler output summarization."""
    duplicate_submission_template: str = (
        "Your submission was not evaluated: the current repository diff is byte-identical to "
        "{% if attempt_index == 0 %}the unmodified reference code (speedup 1.00000x)"
        "{% else %}attempt {{ attempt_index }}, which was already measured at "
        '{{ "%.5f" | format(speedup) }}x{% endif %}. '
        "Re-evaluating the same diff cannot improve your result.\n"
        "This submission did not consume one of your optimization attempts. Make a materially "
        "different change before submitting again. If you have exhausted your ideas, submit again "
        "without making any changes to end the run."
    )
    """Template for rejecting a submission whose diff is byte-identical to an already-measured attempt.

    Variables: `attempt_index` (0 = reference baseline, n = n-th optimization attempt) and `speedup`.
    """
    max_attempts: int = 5
    """Maximum number of optimization attempts before stopping."""
    action_regex: str = r"```bash\s*\n(.*?)\n```"
    """Regex for extracting bash commands from model responses (fallback for non-tool-call models)."""
    build_command: str = "/build.sh"
    """Command that rebuilds the repository after changes."""
    test_command: str = "/run_tests.sh"
    """Command that runs the correctness test suite."""
    profile_command: str = "python /profile_prob_script.py"
    """Command that times and profiles the workload."""
    reference_profile_command: str = "python /profile_prob_script.py --reference"
    """profile_command that records the reference baseline."""
    workload_script: str = "/perf_script.py"
    """Container path of the workload script (used in error messages)."""


class PerfAgent(DefaultAgent):
    """Agent that optimizes software performance by iteratively profiling and applying LLM-suggested changes."""

    def __init__(self, model: Model, env: Environment, *, config_class: type = PerfAgentConfig, **kwargs):
        super().__init__(model, env, config_class=config_class, **kwargs)
        self.opt_attempts: list[OptAttempt] = []
        self.summary_model = self.model
        self._tool_namespace = uuid.uuid4().hex  # keeps this agent's editor undo history apart from others'

    def _render_template_with_vars(self, template: str, **extra_vars) -> str:
        return Template(template, undefined=StrictUndefined).render(**self.get_template_vars(**extra_vars))

    def run(self, task: str = "", **kwargs) -> dict:
        self.extra_template_vars |= {"task": task, **kwargs}
        self.messages = []
        self.opt_attempts = []

        initial_perf_report = self._get_reference_profiler_report()
        self.add_messages(
            self.model.format_message(role="system", content=self._render_template(self.config.system_template)),
            self.model.format_message(
                role="user",
                content=self._render_template_with_vars(
                    self.config.instance_template, initial_perf_report=initial_perf_report
                ),
            ),
        )

        attempt = 0
        rejected_last_submission = False
        while True:
            try:
                self.step()
                rejected_last_submission = False  # the model took a regular action since the last rejection
            except Submitted:
                # Remove the assistant message that triggered submission so it doesn't confuse the model
                if self.messages and self.messages[-1].get("role") == "assistant":
                    self.messages.pop()
                matched = self._find_matching_attempt(self._get_current_diff())
                if matched is not None:
                    # Duplicate of an already-measured diff: re-measuring cannot change the result.
                    if rejected_last_submission:
                        # Re-submitted with no action in between, right after being told it was a
                        # duplicate. The model has signalled it is done; end the run.
                        self.logger.info("Duplicate submission immediately after a rejected duplicate; ending run")
                        break
                    rejected_last_submission = True
                    self.logger.info(
                        f"Submission rejected: diff is byte-identical to attempt {matched} "
                        f"(speedup {self.opt_attempts[matched].speedup:.5f}x); attempt not consumed"
                    )
                    self.add_messages(
                        self.model.format_message(role="user", content=self._render_duplicate_submission(matched))
                    )
                    continue
                attempt += 1
                self.logger.info(f"Model reports completion (attempt {attempt}/{self.config.max_attempts})")
                profiler_report = self._run_profiler(reference=False)
                self.logger.info("Obtained profiler report")  # set log level to debug to see
                self.logger.info(profiler_report)
                self.add_messages(self.model.format_message(role="user", content=profiler_report))
                if attempt >= self.config.max_attempts:
                    break
            except LimitsExceeded:
                self.logger.info(f"Limits exceeded. Optimization attempts: {len(self.opt_attempts) - 1}")
                break
            except litellm.exceptions.ContextWindowExceededError:
                self.logger.info(f"Context window exceeded. Optimization attempts: {len(self.opt_attempts) - 1}")
                break
            except litellm.exceptions.BadRequestError:
                self.logger.info(f"Bad request. Optimization attempts: {len(self.opt_attempts) - 1}")
                break
            except InterruptAgentFlow as e:
                self.add_messages(*e.messages)
            except Exception as e:
                self.handle_uncaught_exception(e)
                raise
            finally:
                self.save(self.config.output_path)

        self._flush_unrecorded_diff()

        exit_extra = {
            "exit_status": "completed",
            "submission": "",
            "opt_attempts": self._get_opt_attempts(),
        }
        self.add_messages(self.model.format_message(role="exit", content="Profiling complete", extra=exit_extra))
        self.save(self.config.output_path)
        return exit_extra

    def step(self) -> list[dict]:
        response = self.query()
        self.logger.info(f"LLM response: {response['content']}")
        return self._get_observation(response)

    def _get_observation(self, response: dict) -> list[dict]:
        # Execute actions from the response in the environment
        actions = response.get("extra", {}).get("actions", [])
        if actions:
            outputs = []
            for action in actions:
                if action.get("tool", "bash") == "bash" and action.get("command", "").lower() == "true":
                    raise Submitted(self.model.format_message(
                        role="exit", content="",
                        extra={"exit_status": "Submitted", "submission": ""},
                    ))
                outputs.append(self._execute_action(action))
            return self.add_messages(
                *self.model.format_observation_messages(response, outputs, self.get_template_vars())
            )

        # Fallback in case there aren't any tool calls which shouldn't happen as tool_choice is set to required on the config
        parsed = self._parse_action(response)
        command = parsed["action"]
        if command.lower() == "true":
            raise Submitted(self.model.format_message(
                role="exit", content="",
                extra={"exit_status": "Submitted", "submission": ""},
            ))
        output = self.env.execute({"command": command})
        observation = self._render_template_with_vars(self.config.action_observation_template, output=output)
        return self.add_messages(self.model.format_message(role="user", content=observation))

    def _execute_action(self, action: dict) -> dict:
        """Run one action: bash straight through the environment, anything else through the
        registered tool of that name (perfagent.tools), which itself executes in the environment."""
        tool_name = action.get("tool", "bash")
        if tool_name == "bash":
            return self.env.execute(action)
        tool = get_tool(tool_name)
        if tool is None:
            return {"output": f"Unknown tool: {tool_name}", "returncode": 1}
        return tool.execute(self.env, action.get("args", {}), namespace=self._tool_namespace)

    def _parse_action(self, response: dict) -> dict:
        content = response.get("content", "")
        actions = re.findall(self.config.action_regex, content, re.DOTALL)
        if len(actions) == 1:
            return {"action": actions[0].strip(), **response}

        # Some models omit closing backticks
        patched = content + "\n```"
        actions = re.findall(self.config.action_regex, patched, re.DOTALL)
        if len(actions) == 1:
            return {"action": actions[0].strip(), **response}

        raise FormatError(self.model.format_message(
            role="user",
            content=self._render_template_with_vars(self.config.format_error_template, actions=actions),
        ))

    def _get_current_diff(self) -> str:
        # Return the current worktree diff, use the same command that _run_profiler uses.
        return self.env.execute({"command": "git add -A && git diff --cached"}, cwd="/testbed")["output"]

    def _find_matching_attempt(self, diff: str) -> int | None:
        for idx, attempt in enumerate(self.opt_attempts):
            if attempt.diff.strip() == diff.strip():
                return idx
        return None

    def _render_duplicate_submission(self, attempt_index: int) -> str:
        return self._render_template_with_vars(
            self.config.duplicate_submission_template,
            attempt_index=attempt_index,
            speedup=self.opt_attempts[attempt_index].speedup,
        )

    def _flush_unrecorded_diff(self) -> None:
        # If run into LimitsExceeded error, try to use the diff in the current repo as an attempt
        try:
            diff = self._get_current_diff()
            if not diff.strip() or self._find_matching_attempt(diff) is not None:
                return
            self.logger.info("Unrecorded working-tree diff at run end; running validate-and-record pipeline")
            attempts_before = len(self.opt_attempts)
            report = self._run_profiler(reference=False)
            if len(self.opt_attempts) > attempts_before:
                self.logger.info(f"Recorded final attempt (speedup {self.opt_attempts[-1].speedup:.5f}x)")
            else:
                self.logger.info(f"Final working-tree diff failed validation; not recorded:\n{report}")
        except Exception as e:
            self.logger.warning(f"Failed to flush final working-tree diff: {e}")

    def _get_reference_profiler_report(self) -> str:
        """Run the profiler on the base repository, before any changes are made."""
        report = self._run_profiler(reference=True)
        self.logger.info("Reference profiler report obtained")
        self.logger.info(report)
        return report

    def _run_profiler(self, reference: bool = False) -> str:
        # Build, test, and profile the code. 
        if not reference:
            build_output = self.env.execute({"command": self.config.build_command})
            if build_output["returncode"] != 0:
                header = (
                    "The changes you made produced the following error when building "
                    f"the repository running: `{self.config.build_command}`."
                )
                return self._render_template_with_vars(
                    self.config.runtime_error_template, header=header, output=build_output
                )

            test_output = self.env.execute({"command": self.config.test_command})
            if test_output["returncode"] != 0:
                header = (
                    "The changes you made produced the following error when running "
                    f"the test suite using: `{self.config.test_command}`."
                )
                return self._render_template_with_vars(
                    self.config.runtime_error_template, header=header, output=test_output
                )

        profiler_cmd = self.config.reference_profile_command if reference else self.config.profile_command
        profiler_output = self.env.execute({"command": profiler_cmd}, cwd="/")
        if profiler_output["returncode"] != 0:
            if reference:
                raise RuntimeError(
                    f"Running profiler on reference should never error. Output: {profiler_output['output']}"
                )
            header = (
                "The changes you made produced the following error when running "
                f"the test script: `{self.config.workload_script}`."
            )
            return self._render_template_with_vars(
                self.config.runtime_error_template, header=header, output=profiler_output
            )

        runtime = self._get_runtime(profiler_output["output"])
        perf_report_summary = self._get_profiler_summary(profiler_output, runtime=runtime, reference=reference)

        if reference:
            self.opt_attempts.append(
                OptAttempt(runtime=runtime, speedup=1.0, perf_report=perf_report_summary, diff="")
            )
            return perf_report_summary

        speedup = self.opt_attempts[0].runtime / runtime
        self.logger.info(
            f"Speedup: {speedup:.5f}x (ref: {self.opt_attempts[0].runtime:.5f}ms, current: {runtime:.5f}ms)"
        )
        self.logger.info(
            f"Perf report summary:\n{perf_report_summary}\n"
        )
        diff = self.env.execute({"command": "git add -A && git diff --cached"}, cwd="/testbed")["output"]
        self.opt_attempts.append(
            OptAttempt(runtime=runtime, speedup=speedup, perf_report=perf_report_summary, diff=diff)
        )
        return self._render_template_with_vars(
            self.config.test_script_perf_template,
            perf_report_summary=perf_report_summary,
            speedup=speedup,
            ref_runtime=self.opt_attempts[0].runtime,
            current_runtime=runtime,
        )

    def _get_profiler_summary(self, profiler_output: dict, runtime: float, reference: bool) -> str:
        """Make a call to LLM to summarize profiler output. Pass in tools=[] to prevent the model from emitting tool calls."""
        extra = {"profiler_output": profiler_output["output"], "current_runtime": runtime}
        if not reference and self.opt_attempts:
            extra["ref_runtime"] = self.opt_attempts[0].runtime
            extra["speedup"] = self.opt_attempts[0].runtime / runtime
        msg = self._render_template_with_vars(self.config.perf_summary_template, **extra)
        messages = [
            {
                "role": "system",
                "content": "You are a performance analyst summarizing py-spy sampling profiles of Python programs.",
            },
            {"role": "user", "content": msg},
        ]
        response = self.summary_model.query(messages, tools=[])
        self.cost += response.get("extra", {}).get("cost", 0.0)
        return response["content"]

    def _get_runtime(self, output: str) -> float:
        for line in output.splitlines():
            line = line.strip()
            if "_runtime" in line:
                try:
                    return float(line.split(":")[1])
                except Exception:
                    raise RuntimeError(f"Cannot parse runtime from line: {line}")
        raise RuntimeError(f"Cannot parse runtime from output: {output}")

    def _get_opt_attempts(self) -> list[dict]:
        return [asdict(attempt) for attempt in self.opt_attempts[1:]]

    def serialize(self, *extra_dicts) -> dict:
        return super().serialize({"opt_attempts": self._get_opt_attempts()}, *extra_dicts)
