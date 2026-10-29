"""Behaviour of reading each Source's copy, from real throwaway repositories and a fake host."""

from enum import IntEnum
from pathlib import Path

import pytest

import repo_settings
from repo_settings import Missing, RemoteFiles, Settings, Source, Unlocatable

FILE = ".config/ianf-thing.toml"


class Version(IntEnum):
    V1 = 1


def thing(colour: str) -> str:
    return f'version = 1\ncolour = "{colour}"\n'


def colour(read: object) -> object:
    assert isinstance(read, Settings), read
    return read.table["colour"]


class FakeHost(RemoteFiles):
    def __init__(self, branch: str, files: dict[tuple[str, str], str]) -> None:
        self.name = "example.org/team/app"
        self.branch = branch
        self.files = files

    def default_branch(self) -> str:
        return self.branch

    def file(self, revision: str, path: str) -> str | None:
        return self.files.get((revision, path))


def test_this_worktree_is_read_as_it_is_on_disk(repos):
    repo = repos.repo("repo", "main")
    repos.commit(repo, FILE, thing("red"))
    repos.write(repo, FILE, thing("blue"))
    read = repo_settings.read(Source.LOCAL_THIS_WORKTREE, repo, "thing", Version)
    assert colour(read) == "blue"
    assert read == Settings(Version.V1, {"colour": "blue"}, str(repo / FILE), None)


def test_this_worktree_is_found_from_a_subdirectory(repos):
    repo = repos.repo("repo", "main")
    repos.commit(repo, FILE, thing("red"))
    (repo / "app").mkdir()
    assert (
        colour(repo_settings.read(Source.LOCAL_THIS_WORKTREE, repo / "app", "thing", Version))
        == "red"
    )


def test_the_main_worktree_is_read_from_a_linked_one(repos):
    repo = repos.repo("repo", "main")
    repos.commit(repo, FILE, thing("red"))
    linked = repos.worktree(repo, "repo-wt1")
    repos.write(repo, FILE, thing("blue"))
    read = repo_settings.read(Source.LOCAL_MAIN_WORKTREE, linked, "thing", Version)
    assert colour(read) == "blue"


def test_the_default_branch_is_read_as_committed_whatever_is_on_disk(repos):
    repo = repos.repo("repo", "main")
    repos.commit(repo, FILE, thing("red"))
    repos.git("-C", repo, "switch", "--quiet", "--create", "spike")
    repos.commit(repo, FILE, thing("green"))
    repos.write(repo, FILE, thing("blue"))
    read = repo_settings.read(Source.LOCAL_DEFAULT_BRANCH, repo, "thing", Version)
    assert colour(read) == "red"
    assert isinstance(read, Settings)
    assert read.where == f"{FILE} on main"


def test_the_default_branch_is_the_one_git_default_branch_tells(repos):
    repo = repos.repo("repo", "main")
    repos.commit(repo, FILE, thing("red"))
    repos.git("-C", repo, "switch", "--quiet", "--create", "develop")
    repos.commit(repo, FILE, thing("green"))
    repos.git("-C", repo, "config", "default-branch.name", "develop")
    assert (
        colour(repo_settings.read(Source.LOCAL_DEFAULT_BRANCH, repo, "thing", Version)) == "green"
    )


def test_a_worktree_whose_own_copy_differs_from_the_default_branchs_is_told_it_isnt_used(repos):
    repo = repos.repo("repo", "main")
    repos.commit(repo, FILE, thing("red"))
    linked = repos.worktree(repo, "repo-wt1")
    repos.write(linked, FILE, thing("blue"))
    read = repo_settings.read(Source.LOCAL_DEFAULT_BRANCH, linked, "thing", Version)
    assert isinstance(read, Settings)
    assert read.ignored == linked / FILE
    assert repo_settings.notice(read) == (
        f"Your edits to {linked / FILE} aren't used: {FILE} on main is."
    )


def test_a_worktree_whose_copy_matches_the_one_read_is_told_nothing(repos):
    repo = repos.repo("repo", "main")
    repos.commit(repo, FILE, thing("red"))
    linked = repos.worktree(repo, "repo-wt1")
    read = repo_settings.read(Source.LOCAL_DEFAULT_BRANCH, linked, "thing", Version)
    assert isinstance(read, Settings)
    assert read.ignored is None


def test_a_linked_worktree_whose_copy_differs_from_the_main_worktrees_is_told_it_isnt_used(repos):
    repo = repos.repo("repo", "main")
    repos.commit(repo, FILE, thing("red"))
    linked = repos.worktree(repo, "repo-wt1")
    repos.write(linked, FILE, thing("blue"))
    read = repo_settings.read(Source.LOCAL_MAIN_WORKTREE, linked, "thing", Version)
    assert isinstance(read, Settings)
    assert read.ignored == linked / FILE


def test_a_file_missing_from_a_worktree_is_missing_there(repos):
    repo = repos.repo("repo", "main")
    assert repo_settings.read(Source.LOCAL_THIS_WORKTREE, repo, "thing", Version) == Missing(
        str(repo / FILE)
    )


def test_a_file_on_disk_but_not_committed_is_missing_from_the_default_branch(repos):
    repo = repos.repo("repo", "main")
    repos.write(repo, FILE, thing("red"))
    read = repo_settings.read(Source.LOCAL_DEFAULT_BRANCH, repo, "thing", Version)
    assert read == Missing(f"{FILE} on main")


def test_a_default_branch_nothing_names_says_how_to_name_it(repos):
    repo = repos.repo("repo", "main")
    repos.git("-C", repo, "branch", "master")
    read = repo_settings.read(Source.LOCAL_DEFAULT_BRANCH, repo, "thing", Version)
    assert isinstance(read, Unlocatable)
    assert "git config default-branch.name <branch>" in read.message


def test_a_default_branch_with_no_local_branch_says_so(repos, tmp_path: Path):
    origin = repos.repo("origin", "main")
    clone = tmp_path / "clone"
    repos.git("clone", "--quiet", origin, clone)
    repos.git("-C", clone, "switch", "--quiet", "--create", "spike")
    repos.git("-C", clone, "branch", "--quiet", "--delete", "--force", "main")
    read = repo_settings.read(Source.LOCAL_DEFAULT_BRANCH, clone, "thing", Version)
    assert isinstance(read, Unlocatable)
    assert read.message == f"There's no local main branch to read {FILE} from."


def test_a_copy_that_cant_be_read_says_why(repos):
    repo = repos.repo("repo", "main")
    (repo / FILE).mkdir(parents=True)
    read = repo_settings.read(Source.LOCAL_THIS_WORKTREE, repo, "thing", Version)
    assert isinstance(read, Unlocatable)
    assert read.message.startswith(f"Can't read {repo / FILE}: ")


def test_outside_a_repository_no_local_copy_can_be_found(tmp_path: Path):
    for source in (
        Source.LOCAL_THIS_WORKTREE,
        Source.LOCAL_MAIN_WORKTREE,
        Source.LOCAL_DEFAULT_BRANCH,
    ):
        read = repo_settings.read(source, tmp_path, "thing", Version)
        assert isinstance(read, Unlocatable), source


def test_the_code_hosts_default_branch_is_read_without_a_clone():
    host = FakeHost("trunk", {("trunk", FILE): thing("red"), ("main", FILE): thing("blue")})
    read = repo_settings.read(Source.REMOTE_DEFAULT_BRANCH, host, "thing", Version)
    assert read == Settings(
        Version.V1, {"colour": "red"}, f"{FILE} on trunk at example.org/team/app", None
    )


def test_a_file_the_code_host_doesnt_have_is_missing_there():
    read = repo_settings.read(Source.REMOTE_DEFAULT_BRANCH, FakeHost("main", {}), "thing", Version)
    assert read == Missing(f"{FILE} on main at example.org/team/app")


def test_the_text_of_a_copy_can_be_fetched_unparsed():
    host = FakeHost("main", {("main", FILE): "not toml ="})
    found = repo_settings.fetch(Source.REMOTE_DEFAULT_BRANCH, host, "thing")
    assert isinstance(found, repo_settings.Text)
    assert found.text == "not toml ="


def test_a_local_source_needs_a_directory_and_a_remote_one_its_host(tmp_path: Path):
    with pytest.raises(TypeError):
        repo_settings.read(Source.LOCAL_THIS_WORKTREE, FakeHost("main", {}), "thing", Version)
    with pytest.raises(TypeError):
        repo_settings.read(Source.REMOTE_DEFAULT_BRANCH, tmp_path, "thing", Version)
