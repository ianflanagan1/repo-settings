"""A repository's settings that its team shares, committed in its .config/ directory: one TOML
file for each purpose, named ianf-<purpose>.toml, such as .config/ianf-tracker.toml for where its
issues go. The prefix keeps them apart from other tools' files there.

A repository holds many copies of each file: one in each worktree, one on each branch, and the
code host's. Each tool says which it reads, as a Source, by three choices:

    LOCAL or REMOTE     from a clone on this machine, or from the code host, with no clone
    THIS or MAIN        the worktree or branch you're in, or the main worktree
         or DEFAULT     ... or the default branch
    WORKTREE or BRANCH  the files on disk, uncommitted edits included, or what's committed

    read(Source.LOCAL_DEFAULT_BRANCH, Path.cwd(), "worktree-env", Version)

Each file sets the version of the format it's written in, as version = 1, beside its settings.
The tool that owns the file keeps a JSON Schema for each version, as
schema/ianf-<purpose>.v<version>.json, and the file names its schema on its first line, as
#:schema <url>, for editors to check it against. A change that a file written for the old
format still meets, such as a new optional setting, keeps the version; any other change makes a
new one.

A tool lists the versions it reads as an IntEnum and matches on the one a file sets:

    class Version(IntEnum):
        V1 = 1

A tool writes settings into the files on disk of the worktrees a Target names, setting each key
in each copy and keeping the rest of that copy as it is, its comments and uncommitted edits
included. A copy that's missing is created, starting as its NewFile says, and a missing table is
created with it:

    write(Target.EVERY_WORKTREE, Path.cwd(), "repo-tools", NewFile(Version.V1, SCHEMA),
          [Assignment((), "integration", "local")])
"""

import subprocess
import tomllib
from abc import ABC, abstractmethod
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum, IntEnum
from pathlib import Path
from typing import assert_never, final

import git_default_branch
import tomlkit
import tomlkit.exceptions

from repo_settings import checkouts

DIRECTORY = ".config"
PREFIX = "ianf-"


class Source(Enum):
    """Which copy of a repository's settings file to read."""

    LOCAL_THIS_WORKTREE = "this worktree"
    """The file in the worktree you're in, as it is on disk."""
    LOCAL_MAIN_WORKTREE = "the main worktree"
    """The file in the repository's main worktree, as it is on disk, whichever branch it has
    checked out."""
    LOCAL_DEFAULT_BRANCH = "the default branch"
    """The file as committed on the local default branch, as git-default-branch tells it,
    without asking the remote."""
    REMOTE_DEFAULT_BRANCH = "the code host's default branch"
    """The file as committed on the default branch on the code host, read through its
    RemoteFiles."""


class Target(Enum):
    """Which worktrees' copies of a repository's settings file to write, as they are on disk."""

    THIS_WORKTREE = "this worktree"
    """The worktree the directory given is in."""
    MAIN_WORKTREE = "the main worktree"
    """The repository's main worktree, whichever branch it has checked out."""
    EVERY_WORKTREE = "every worktree"
    """The main worktree and each linked one, each copy edited on its own."""


type Value = (
    str | int | float | bool | datetime | date | time | Sequence[Value] | Mapping[str, Value]
)
"""A value a TOML file can hold."""


@final
@dataclass(frozen=True)
class Assignment:
    """A key to set in a settings file, and its value."""

    table: tuple[str, ...]
    """The table the key is in, by its names from the top of the file, such as ("jira",) for
    [jira] or ("jira", "fields") for [jira.fields]; () for the top of the file itself."""
    key: str
    value: Value


@final
@dataclass(frozen=True)
class NewFile[V: IntEnum]:
    """What a settings file starts as when it's created: the version of its format, and the URL
    of that version's schema, for its #:schema line."""

    version: V
    schema: str


class RemoteFiles(ABC):
    """A repository on a code host, read without a clone. Each method raises when the host can't
    be reached or the login can't see the repository, as the adapter's tool reports it."""

    name: str
    """The repository as people name it, such as "bitbucket.org/team/app"."""

    @abstractmethod
    def default_branch(self) -> str:
        """The branch the host calls the repository's default."""

    @abstractmethod
    def file(self, revision: str, path: str) -> str | None:
        """The text of the file at path in revision, or None when it has none."""


@final
@dataclass(frozen=True)
class Text:
    """A copy of a settings file, as text."""

    text: str
    where: str
    """Which copy it is, for messages, such as "/repo/.config/ianf-tracker.toml" or
    ".config/ianf-tracker.toml on main"."""
    ignored: Path | None
    """This worktree's own copy of the file, when it differs from this one, so its edits aren't
    being used."""


@final
@dataclass(frozen=True)
class Settings[V: IntEnum]:
    version: V
    table: dict[str, object]
    """The file's settings, without its version."""
    where: str
    """Which copy they were read from, for messages."""
    ignored: Path | None
    """This worktree's own copy of the file, when it differs from the one read."""


@final
@dataclass(frozen=True)
class Missing:
    """There's no such file in the copy looked in."""

    where: str


@final
@dataclass(frozen=True)
class Unlocatable:
    """The copy can't be found or read, such as the default branch when nothing says which it
    is: a message, then any lines of detail."""

    message: str
    details: tuple[str, ...]


@final
@dataclass(frozen=True)
class Invalid:
    """Why a file's settings can't be read: a message, then any lines of detail."""

    message: str
    details: tuple[str, ...]


@final
@dataclass(frozen=True)
class Written:
    """A copy of the file was changed, or created when it was missing."""

    path: Path
    created: bool


@final
@dataclass(frozen=True)
class Unchanged:
    """A copy of the file already had every value written to it, so it was left as it was."""

    path: Path


def location(purpose: str) -> str:
    """Where a repository keeps the settings for purpose, from its root."""
    return f"{DIRECTORY}/{PREFIX}{purpose}.toml"


def read[V: IntEnum](
    source: Source, repo: Path | RemoteFiles, purpose: str, versions: type[V]
) -> Settings[V] | Missing | Unlocatable | Invalid:
    """The settings for purpose in source's copy of them. repo is a directory in a clone for a
    LOCAL source, or the repository's RemoteFiles for a REMOTE one."""
    found = fetch(source, repo, purpose)
    if not isinstance(found, Text):
        return found
    parsed = loads(found.text, found.where, versions)
    if isinstance(parsed, Invalid):
        return parsed
    return Settings(parsed.version, parsed.table, found.where, found.ignored)


def fetch(source: Source, repo: Path | RemoteFiles, purpose: str) -> Text | Missing | Unlocatable:
    """The text of source's copy of the settings for purpose, as read describes."""
    file = location(purpose)
    match source:
        case Source.LOCAL_THIS_WORKTREE:
            return _in_worktree(checkouts.this_worktree(_directory(repo)), file, _directory(repo))
        case Source.LOCAL_MAIN_WORKTREE:
            return _in_worktree(checkouts.main_worktree(_directory(repo)), file, _directory(repo))
        case Source.LOCAL_DEFAULT_BRANCH:
            return _on_default_branch(_directory(repo), file)
        case Source.REMOTE_DEFAULT_BRANCH:
            return _on_host(_remote(repo), file)
        case _:
            assert_never(source)


def read_file[V: IntEnum](file: Path, versions: type[V]) -> Settings[V] | Missing | Invalid:
    """The settings in a file named outright, rather than by a Source."""
    try:
        text = file.read_text()
    except FileNotFoundError:
        return Missing(str(file))
    parsed = loads(text, str(file), versions)
    if isinstance(parsed, Invalid):
        return parsed
    return Settings(parsed.version, parsed.table, str(file), None)


def loads[V: IntEnum](text: str, where: str, versions: type[V]) -> Settings[V] | Invalid:
    """The settings in a file's text; where names the file in what's wrong with them."""
    try:
        table = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        return Invalid(f"{where} isn't valid TOML.", (str(error),))
    return parse(table, where, versions)


def parse[V: IntEnum](table: dict, where: str, versions: type[V]) -> Settings[V] | Invalid:
    """The settings in a parsed table, such as a file's or one copied into another file."""
    known = {version.value: version for version in versions}
    if "version" not in table:
        latest = max(known)
        return Invalid(
            f"No version in {where}.",
            (f"Add version = {latest} beside its settings: the version of the format they're in.",),
        )
    number = table["version"]
    if type(number) is not int:
        return Invalid(f"version in {where} must be a whole number.", ())
    if number not in known:
        numbers = [str(n) for n in sorted(known)]
        names = " and ".join(", ".join(numbers).rsplit(", ", 1))
        return Invalid(
            f"{where} is version {number}, which this tool doesn't read.",
            (
                f"It reads version{'s' if len(numbers) > 1 else ''} {names}. Upgrade the tool, or"
                " write the file in a version it reads.",
            ),
        )
    table = {k: v for k, v in table.items() if k != "version"}
    return Settings(known[number], table, where, None)


def write[V: IntEnum](
    target: Target,
    directory: Path,
    purpose: str,
    new_file: NewFile[V],
    assignments: Sequence[Assignment],
) -> tuple[Written | Unchanged | Invalid | Unlocatable, ...]:
    """Each assignment made in each of target's worktrees' copies of the settings for purpose,
    as edit makes them, and what came of each copy; directory is a directory in a clone. One copy
    that can't be written doesn't stop the others. Unlocatable alone when target names no
    worktree, such as outside a repository."""
    roots = _worktrees(target, directory)
    if not roots:
        return (Unlocatable(f"{directory} isn't in a worktree of a git repository.", ()),)
    return tuple(_write_copy(root / location(purpose), new_file, assignments) for root in roots)


def edit[V: IntEnum](
    text: str | None, where: str, new_file: NewFile[V], assignments: Sequence[Assignment]
) -> str | Invalid:
    """A settings file's text with each assignment made in order, creating any table it names
    that's missing, and keeping the rest of the text as it was; where names the file in what's
    wrong. text is None for a file that doesn't exist yet, which starts as new_file says. A file
    that's not in a version of new_file's format, or that can't hold a table an assignment names,
    is invalid, so it's left for a person to fix."""
    if text is None:
        text = f"#:schema {new_file.schema}\nversion = {new_file.version.value}\n"
    try:
        document = tomlkit.parse(text)
    except tomlkit.exceptions.ParseError as error:
        return Invalid(f"{where} isn't valid TOML.", (str(error),))
    for assignment in assignments:
        table = _table(document, assignment, where)
        if isinstance(table, Invalid):
            return table
        if table.get(assignment.key) != assignment.value:  # so an equal value keeps its spelling
            table[assignment.key] = assignment.value
    edited = tomlkit.dumps(document)
    checked = loads(edited, where, type(new_file.version))
    return checked if isinstance(checked, Invalid) else edited


def notice(settings: Settings | Text) -> str | None:
    """What to tell a person whose own copy of the file isn't the one used, or None."""
    if settings.ignored is None:
        return None
    return f"Your edits to {settings.ignored} aren't used: {settings.where} is."


def _in_worktree(root: Path | None, file: str, directory: Path) -> Text | Missing | Unlocatable:
    if root is None:
        return Unlocatable(f"{directory} isn't in a worktree of a git repository.", ())
    path = root / file
    try:
        text = path.read_text()
    except FileNotFoundError:
        return Missing(str(path))
    except OSError as error:
        return Unlocatable(f"Can't read {path}: {error.strerror}.", ())
    return Text(text, str(path), _ignored(directory, file, text))


def _on_default_branch(directory: Path, file: str) -> Text | Missing | Unlocatable:
    facts = git_default_branch.read(directory, ask_remote=False)
    if facts is None:
        return Unlocatable(f"{directory} isn't in a git repository.", ())
    branch = git_default_branch.choose(facts)
    if branch is None:
        return Unlocatable(git_default_branch.why_unknown(facts), ())
    if _git(directory, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}") is None:
        return Unlocatable(
            f"There's no local {branch} branch to read {file} from.",
            (f"{branch} is the default branch: create it, as git branch {branch} <start>.",),
        )
    where = f"{file} on {branch}"
    text = _git(directory, "cat-file", "-p", f"refs/heads/{branch}:{file}")
    if text is None:
        return Missing(where)
    return Text(text, where, _ignored(directory, file, text))


def _on_host(remote: RemoteFiles, file: str) -> Text | Missing:
    branch = remote.default_branch()
    where = f"{file} on {branch} at {remote.name}"
    text = remote.file(branch, file)
    return Missing(where) if text is None else Text(text, where, None)


def _ignored(directory: Path, file: str, used: str) -> Path | None:
    """This worktree's copy of file, when it has one that differs from used."""
    root = checkouts.this_worktree(directory)
    if root is None:
        return None
    try:
        own = (root / file).read_text()
    except FileNotFoundError:
        return None
    return None if own == used else root / file


def _worktrees(target: Target, directory: Path) -> tuple[Path, ...] | None:
    match target:
        case Target.THIS_WORKTREE:
            return _one(checkouts.this_worktree(directory))
        case Target.MAIN_WORKTREE:
            return _one(checkouts.main_worktree(directory))
        case Target.EVERY_WORKTREE:
            return checkouts.every_worktree(directory)
        case _:
            assert_never(target)


def _one(root: Path | None) -> tuple[Path, ...] | None:
    return None if root is None else (root,)


def _write_copy[V: IntEnum](
    path: Path, new_file: NewFile[V], assignments: Sequence[Assignment]
) -> Written | Unchanged | Invalid | Unlocatable:
    try:
        text = path.read_text()
    except FileNotFoundError:
        text = None
    except OSError as error:
        return Unlocatable(f"Can't read {path}: {error.strerror}.", ())
    edited = edit(text, str(path), new_file, assignments)
    if isinstance(edited, Invalid):
        return edited
    if edited == text:
        return Unchanged(path)
    path.parent.mkdir(exist_ok=True)
    path.write_text(edited)
    return Written(path, created=text is None)


def _table(
    document: MutableMapping[str, object], assignment: Assignment, where: str
) -> MutableMapping[str, object] | Invalid:
    """The table in document that assignment's key is in, created when it's missing."""
    table = document
    for depth, name in enumerate(assignment.table):
        if name not in table:
            table[name] = tomlkit.table()
        inner = table[name]
        if not isinstance(inner, MutableMapping):
            names = ".".join(assignment.table[: depth + 1])
            return Invalid(
                f"{names} in {where} isn't a table, so {assignment.key} can't be set in it.", ()
            )
        table = inner
    return table


def _directory(repo: Path | RemoteFiles) -> Path:
    if not isinstance(repo, Path):
        raise TypeError("A LOCAL source reads from a directory in a clone.")
    return repo


def _remote(repo: Path | RemoteFiles) -> RemoteFiles:
    if not isinstance(repo, RemoteFiles):
        raise TypeError("A REMOTE source reads through the repository's RemoteFiles.")
    return repo


def _git(directory: Path, *args: str) -> str | None:
    """git's output in directory, unstripped, or None when it fails."""
    result = subprocess.run(
        ["git", "-C", str(directory), *args],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    return result.stdout if result.returncode == 0 else None
