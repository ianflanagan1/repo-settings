"""Behaviour of writing to each Target's worktrees, in real throwaway repositories."""

import shutil
from enum import IntEnum
from pathlib import Path

import repo_settings
from repo_settings import (
    Assignment,
    Invalid,
    NewFile,
    Settings,
    Source,
    Target,
    Unchanged,
    Unlocatable,
    Written,
)

FILE = ".config/ianf-thing.toml"
SCHEMA = "https://example.org/schema/ianf-thing.v1.json"
RED = (Assignment((), "colour", "red"),)


class Version(IntEnum):
    V1 = 1


NEW = NewFile(Version.V1, SCHEMA)


def write(target: Target, directory: Path):
    return repo_settings.write(target, directory, "thing", NEW, RED)


def test_this_worktree_is_the_one_a_subdirectory_is_in(repos):
    repo = repos.repo("repo", "main")
    (repo / "app").mkdir()
    assert write(Target.THIS_WORKTREE, repo / "app") == (Written(repo / FILE, created=True),)
    assert (repo / FILE).read_text() == f'#:schema {SCHEMA}\nversion = 1\ncolour = "red"\n'


def test_what_is_written_reads_back(repos):
    repo = repos.repo("repo", "main")
    write(Target.THIS_WORKTREE, repo)
    read = repo_settings.read(Source.LOCAL_THIS_WORKTREE, repo, "thing", Version)
    assert read == Settings(Version.V1, {"colour": "red"}, str(repo / FILE), None)


def test_the_main_worktree_is_written_from_a_linked_one(repos):
    repo = repos.repo("repo", "main")
    linked = repos.worktree(repo, "repo-wt1")
    assert write(Target.MAIN_WORKTREE, linked) == (Written(repo / FILE, created=True),)
    assert not (linked / FILE).exists()


def test_every_worktree_has_its_own_copy_edited_keeping_its_other_edits(repos):
    repo = repos.repo("repo", "main")
    repos.commit(repo, FILE, 'version = 1\ncolour = "blue"\n')
    linked = repos.worktree(repo, "repo-wt1")
    repos.write(linked, FILE, 'version = 1\ncolour = "blue"\nsize = 2\n')
    assert write(Target.EVERY_WORKTREE, linked) == (
        Written(repo / FILE, created=False),
        Written(linked / FILE, created=False),
    )
    assert (repo / FILE).read_text() == 'version = 1\ncolour = "red"\n'
    assert (linked / FILE).read_text() == 'version = 1\ncolour = "red"\nsize = 2\n'


def test_a_copy_that_already_has_the_value_is_unchanged(repos):
    repo = repos.repo("repo", "main")
    repos.write(repo, FILE, 'version = 1\ncolour   =  "red"\n')
    assert write(Target.THIS_WORKTREE, repo) == (Unchanged(repo / FILE),)
    assert (repo / FILE).read_text() == 'version = 1\ncolour   =  "red"\n'


def test_an_invalid_copy_is_left_as_it_is_and_the_others_still_written(repos):
    repo = repos.repo("repo", "main")
    repos.write(repo, FILE, "version = 9\n")
    linked = repos.worktree(repo, "repo-wt1")
    written = write(Target.EVERY_WORKTREE, repo)
    assert isinstance(written[0], Invalid)
    assert written[1] == Written(linked / FILE, created=True)
    assert (repo / FILE).read_text() == "version = 9\n"


def test_a_worktree_whose_directory_is_gone_is_skipped(repos):
    repo = repos.repo("repo", "main")
    shutil.rmtree(repos.worktree(repo, "repo-wt1"))
    assert write(Target.EVERY_WORKTREE, repo) == (Written(repo / FILE, created=True),)


def test_outside_a_repository_nothing_is_written(tmp_path: Path):
    for target in Target:
        assert write(target, tmp_path) == (
            Unlocatable(f"{tmp_path} isn't in a worktree of a git repository.", ()),
        )
    assert not (tmp_path / FILE).exists()
