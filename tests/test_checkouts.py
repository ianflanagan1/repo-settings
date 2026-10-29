import shutil
from pathlib import Path

from repo_settings.checkouts import every_worktree, main_worktree, this_worktree


def test_this_worktree_is_the_root_of_the_one_a_subdirectory_is_in(repos):
    repo = repos.repo("repo", "main")
    (repo / "app" / "src").mkdir(parents=True)
    assert this_worktree(repo / "app" / "src") == repo


def test_in_a_linked_worktree_this_worktree_is_that_one(repos):
    linked = repos.worktree(repos.repo("repo", "main"), "repo-wt1")
    assert this_worktree(linked) == linked


def test_outside_a_repository_there_is_no_worktree(tmp_path: Path):
    assert this_worktree(tmp_path) is None
    assert main_worktree(tmp_path) is None
    assert every_worktree(tmp_path) is None


def test_the_main_worktree_is_found_from_a_linked_one(repos):
    repo = repos.repo("repo", "main")
    assert main_worktree(repos.worktree(repo, "repo-wt1")) == repo


def test_the_main_worktree_is_found_from_inside_itself(repos):
    repo = repos.repo("repo", "main")
    (repo / "app").mkdir()
    assert main_worktree(repo / "app") == repo


def test_a_bare_repository_has_no_main_worktree(repos, tmp_path: Path):
    bare = tmp_path / "bare.git"
    repos.git("clone", "--quiet", "--bare", repos.repo("origin", "main"), bare)
    assert main_worktree(bare) is None


def test_every_worktree_is_the_main_one_then_each_linked_one(repos):
    repo = repos.repo("repo", "main")
    first = repos.worktree(repo, "repo-wt1")
    second = repos.worktree(repo, "repo-wt2")
    assert every_worktree(second) == (repo, first, second)


def test_every_worktree_leaves_out_one_whose_directory_is_gone(repos):
    repo = repos.repo("repo", "main")
    shutil.rmtree(repos.worktree(repo, "repo-wt1"))
    assert every_worktree(repo) == (repo,)


def test_every_worktree_of_a_bare_repository_is_its_linked_ones(repos, tmp_path: Path):
    bare = tmp_path / "bare.git"
    repos.git("clone", "--quiet", "--bare", repos.repo("origin", "main"), bare)
    linked = repos.worktree(bare, "repo-wt1")
    assert every_worktree(bare) == (linked,)
