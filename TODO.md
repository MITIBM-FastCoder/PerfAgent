# TODO

- [ ] Update the py-spy profiler so that `--native` can be used for all tasks. Currently there are some errors with py-spy when profiling some repositories.
- [ ] Update `testmon` with a custom test selector.
- [ ] Clean up docker images to prevent reward hacking behavior that occurs with newer models
  - [ ] Disable network access and adjust test scripts to use locally cached copies instead
  - [ ] Remove extraneous files that may leak the answer
