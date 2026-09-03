# TODOs

Gaps to close before or shortly after the public release of this repository. Grouped by priority, one checkbox per action.

## Blockers for public release

- [x] `pyproject.toml`: remove the `[tool.hatch.build.targets.wheel.force-include]` block. It duplicated `packages = ["src/perfagent"]` and made `uv build --wheel` / `pip install .` fail with `ValueError: A second file is being added to the wheel archive at the same path: perfagent/assets/gso/repo_config.yaml`. Verified fixed: `uv build --wheel -o /tmp/pa_wheel_check` now succeeds.
- [x] `pyproject.toml`: add `jinja2>=3.1` and `litellm>=1.99` to `dependencies`. `src/perfagent/agent.py` imports `jinja2` and `src/perfagent/model.py` imports `litellm` directly, but neither was declared. Both arrived only transitively, through `mini-swe-agent`. Verified with `uv sync`.
- [ ] Publish the `test_db` artifact (the stable-test-suite archives). Without it, no real instance can run. Once published:
  - Replace the placeholder path in `configs/gso.yaml:4` (`/home/ubuntu/profiling_agent/gso/test_db/test_db`) with the real, publicly reachable path or download instructions.
  - Replace the placeholder path in `configs/swefficiency.yaml:4` (`/home/ubuntu/profiling_agent/swefficiency/test_db/new_test_db`) with the same.
  - Fill in the `> **TODO(maintainers):**` blockquote in `README.md` (under "Test DB") with the actual download URL or generation steps.
  - Update the "missing stable suite artifact" FAQ answer in `README.md` once the fix is a real command, not a placeholder.
- [ ] `src/perfagent/adapters/base.py:49`: fix or remove the dangling reference to "the old repo's `get_test_db.py`" in the `require_artifact` error message. That script is not in this repository, so the message currently sends users to a file they cannot find.
- [ ] Choose and add a `LICENSE` file. The repository currently has none, which makes the code legally unusable by others regardless of publication. Decision on which license deferred to the maintainers.
- [ ] Confirm the `ryandeng1/perfagent` Docker Hub images are public and will stay available long-term. The account owner has confirmed this account stays as the permanent home for these images. Document that confirmation somewhere durable (e.g. this file or a release note), so a future maintainer does not have to re-ask.

## Should fix

- [ ] Commit a `uv.lock` for reproducibility. `uv sync` already generates one locally. It is currently untracked (confirmed via `git status`).
- [ ] `src/perfagent/cli.py:49`: make the `HF_TOKEN` gate conditional. It currently exits for every run, including all 100 SWE-fficiency tasks and 95 of the 102 GSO tasks, none of which contact Hugging Face. Only 7 GSO workload scripts download anything: the two `abetlen__llama-cpp-python` tasks (Qwen2-7B GGUF), `huggingface__datasets-c5464b3`, `huggingface__datasets-ef3b5dd`, `huggingface__tokenizers-bfd9cde`, `huggingface__transformers-211f93a`, and `huggingface__transformers-d51b589`. Gate the check on the resolved instance, after the instance is known. The README table under "Which instances need `HF_TOKEN`" lists what each one pulls.
- [ ] Ship a Kimi-K2 config variant (with the OpenHands structured file-editing tool used in the paper) alongside the existing GPT-5.1 configs. Only `configs/gso.yaml` and `configs/swefficiency.yaml` (GPT-5.1) exist today.
- [ ] Document or publish Docker image sizes and the disk space a full benchmark run needs. Neither is recorded anywhere in the repo today.

## Nice to have

- [ ] Add a test suite. `pyproject.toml` declares `pytest>=8.0` as a dev dependency, but no tests exist in the repository.
- [ ] Add CI (lint, build, and whatever tests exist).
- [ ] Add a `CONTRIBUTING.md`.
- [ ] Add a driver script that loops over all instances of a benchmark, so users do not have to write their own `--run-id` loop (see the README FAQ for the manual version).
- [ ] Parameterize the Docker registry prefix (`IMAGE_REPO` in `src/perfagent/adapters/base.py:9`, currently hardcoded to `"ryandeng1/perfagent"`) so the image source can move without a code change.
