# TODO

- [ ] Verify `py-spy --native` across all tasks.
  - [x] Enable native profiling for the 12 previously exempt SWE-fficiency tasks and verify caller and worker reporting in their baseline images.
  - [ ] Exercise the updated profiler in the remaining 88 SWE-fficiency Lite baseline images.
- [ ] Update `testmon` with a custom test selector.
- [ ] Clean up docker images to prevent reward hacking behavior that occurs with newer models
  - [ ] Disable network access and adjust test scripts to use locally cached copies instead. Note: this can be challenging as some scripts require network access. Disabling only github/pypi also might not be sufficient.
  - [ ] Remove extraneous files that may leak the answer
    - [x] Remove the GSO setup recipe and post-baseline Git history before the agent starts
    - [ ] Update Docker images to remove these scripts after using them
