# repo-settings

`devbox run -- task check` runs ruff and the tests; run it before finishing. `devbox run -- task lint-file -- <files>` formats and fixes the Python files given.

`parse`, `loads`, `notice` and `edit` are pure: test them with plain values in `tests/test_parse.py` and `tests/test_edit.py`. Reading each `Source` and writing each `Target` are the shell, covered by tests against real throwaway repositories in `tests/test_read.py` and `tests/test_write.py`, with a fake `RemoteFiles` for the code host. A new `Source` gets a case in `fetch`'s match, a new `Target` one in `_worktrees`', and each gets its own tests and a row in the README's tables.
