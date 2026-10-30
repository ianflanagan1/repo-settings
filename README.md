# repo-settings

Reads and writes the settings a repository's team shares, such as where its issues go, in the copy each tool says. Every tool that reads or writes them goes through here, so they all find the files the same way, and each one's choice of copy is named where it reads or writes.

Runs on macOS and Linux. Uses [git-default-branch](../git-default-branch) to tell the default branch.

## The files

Each purpose has one file, committed in the repository's `.config/` directory as `ianf-<purpose>.toml`, such as `.config/ianf-tracker.toml`. A file with one purpose is one file, whichever tools read it; `ianf-` keeps them apart from other tools' files there. Only credentials stay on each person's machine.

Each file sets the version of its format, `version = 1`, beside its settings, and names its JSON Schema on its first line, `#:schema <url>`, so editors with a TOML language server check it as you type. The tool that owns the file keeps a schema for each version in its `schema/` folder, as `ianf-<purpose>.v<version>.json`. A change that a file written for the old format still meets, such as a new optional setting, keeps the version; any other change makes a new version, with its own schema, and the tool reads both until every repository has moved.

## Which copy

A repository holds many copies of each file: one in each worktree, one on each branch, and the code host's. A tool names the one it reads as a `Source`, made of three choices:

| Choice | Options |
|---|---|
| Where | `LOCAL`, a clone on this machine, or `REMOTE`, the code host, with no clone |
| Which | `THIS`, the worktree or branch you're in, or `MAIN`, the main worktree, or `DEFAULT`, the default branch |
| What | `WORKTREE`, the files on disk, uncommitted edits included, or `BRANCH`, what's committed |

| Source | Reads | Read by |
|---|---|---|
| `LOCAL_THIS_WORKTREE` | the file on disk in the worktree you're in, so a branch can change it | jira-tools, product-map, repo-list and repo-fix |
| `LOCAL_MAIN_WORKTREE` | the file on disk in the main worktree, whichever branch it has checked out | none yet |
| `LOCAL_DEFAULT_BRANCH` | the file committed on the local default branch, without asking the remote | worktree-env; repo-list and repo-fix, for the trunk's own mode |
| `REMOTE_DEFAULT_BRANCH` | the file committed on the code host's default branch | dora-tools |

`LOCAL_THIS_BRANCH` and `REMOTE_THIS_BRANCH` aren't there, since no tool needs them yet; there's no `REMOTE_*_WORKTREE`, since a code host has no worktree.

A tool picks the copy by whose decision the settings are. Where a branch may change them and try them, it reads its own worktree. Where every checkout must agree, as on the slots worktree-env hands out, it reads the default branch, which every new worktree starts from. Where they're the team's, read with no clone, as dora's are, it reads the code host.

| File | Owner | Read by, and from |
|---|---|---|
| `ianf-tracker.toml` | [jira-tools](../jira-tools) | jira-tools and product-map, this worktree; dora-tools, the code host |
| `ianf-product-map.toml` | [product-map](../product-map) | product-map, this worktree |
| `ianf-worktree-env.toml` | [worktree-env](../worktree-env) | worktree-env, the default branch |
| `ianf-repo-tools.toml` | [repo-tools](../repo-tools) | repo-list and repo-fix, each worktree, and the default branch for the trunk |
| `ianf-dora.toml` | [dora-tools](../dora-tools) | dora-tools, the code host |

When the copy read isn't the one in the worktree you're in, and yours differs from it, the result says so in `ignored`, and `notice(settings)` says it for a person: `Your edits to <file> aren't used: <copy> is.` A tool prints it on stderr, as worktree-env does, so an edit that hasn't reached the copy it reads isn't silently ignored.

## Writing

A tool writes only to files on disk, in the worktrees it names as a `Target`. Committing them is left to you, and so is reaching the code host.

| Target | Writes |
|---|---|
| `THIS_WORKTREE` | the worktree the directory given is in |
| `MAIN_WORKTREE` | the main worktree, whichever branch it has checked out |
| `EVERY_WORKTREE` | the main worktree and each linked one, skipping any whose directory is gone |

A write sets keys, each named by its table and its key, such as `space` in `[jira]`, or `integration` at the top of the file. Each copy is edited on its own, so the rest of it stays as it was, its comments and uncommitted edits included:

- a missing file is created, starting with its `#:schema` line and `version`
- a missing table is created
- a key's value is set, whether or not the key was there

A copy that isn't valid TOML, isn't in a version the tool reads, has no `version`, or holds a value where a table is named is left as it is and reported as `Invalid`, for a person to fix. One such copy doesn't stop the others from being written.

## From Python

```python
from pathlib import Path

import repo_settings
from repo_settings import Invalid, Missing, Settings, Source, Unlocatable

read = repo_settings.read(Source.LOCAL_DEFAULT_BRANCH, Path.cwd(), "worktree-env", Version)
match read:
    case Settings():
        ...  # read.version, read.table, read.where
    case Missing():
        ...  # no such file in that copy: read.where says which
    case Unlocatable():
        ...  # that copy can't be found or read, such as outside a repository
    case Invalid():
        ...  # the file is there but wrong
    case _:
        assert_never(read)
```

`Version` is the tool's `IntEnum` of the versions it reads; match on `read.version` to read each one. A `LOCAL` source takes a directory in a clone; `REMOTE_DEFAULT_BRANCH` takes the repository's `RemoteFiles`, a port with `default_branch()` and `file(revision, path)` that the tool implements over its code host's API, as dora-tools does over repo-tools' forge. `fetch` gives the copy's text unparsed, for a tool that keeps its own messages or the text itself. `read_file` reads a file named outright, such as one given on the command line, and `parse` a table copied into another file, such as a product map's front matter.

To write:

```python
from repo_settings import Assignment, NewFile, Target, Unchanged, Written

SCHEMA = (
    "https://raw.githubusercontent.com/ianflanagan1/repo-tools/main/schema/ianf-repo-tools.v1.json"
)

for copy in repo_settings.write(
    Target.EVERY_WORKTREE,
    Path.cwd(),
    "repo-tools",
    NewFile(Version.V1, SCHEMA),
    [Assignment((), "integration", "local")],
):
    match copy:
        case Written():
            ...  # copy.path, and copy.created when it was missing
        case Unchanged():
            ...  # it already had every value
        case Unlocatable():
            ...  # no such worktree, such as outside a repository, or the copy can't be read
        case Invalid():
            ...  # the copy is there but wrong, so it was left alone
        case _:
            assert_never(copy)
```

`NewFile` is what a missing copy starts as: the version a new file is written in, and its schema's URL. A write checks each result against that version's `IntEnum`, the same one `read` takes. An `Assignment`'s table is a tuple of names from the top of the file: `("jira",)` for `[jira]`, `("jira", "fields")` for `[jira.fields]`, and `()` for the top of the file. `edit` makes the same change to a file's text without touching disk.

`repo_settings.checkouts` has the lookups the sources and targets are built on: `this_worktree(directory)` and `main_worktree(directory)`, each the worktree's root, or `None` outside a repository or, for the main one, in a bare repository; and `every_worktree(directory)`, each worktree's root, the main one first.

Depend on it from another tool with:

```toml
[tool.uv.sources]
repo-settings = { path = "../repo-settings", editable = true }
git-default-branch = { path = "../git-default-branch", editable = true }
```

uv reads sources only from the project it's syncing, so a tool names git-default-branch's source too.

## Setup

```sh
cd ~/projects/cli/repo-settings
devbox run -- task setup   # uv sync, building .venv
```
