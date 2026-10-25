from enum import IntEnum
from pathlib import Path

import repo_settings
from repo_settings import Invalid, Missing, Settings


class Version(IntEnum):
    V1 = 1
    V2 = 2


def test_a_purposes_settings_are_in_the_config_directory_under_the_publishers_prefix():
    assert repo_settings.location("tracker") == ".config/ianf-tracker.toml"


def test_settings_are_the_table_without_its_version():
    read = repo_settings.parse({"version": 2, "site": "x"}, "here", Version)
    assert read == Settings(Version.V2, {"site": "x"}, "here", None)


def test_a_table_without_a_version_says_to_add_the_latest():
    read = repo_settings.parse({"site": "x"}, "here", Version)
    assert isinstance(read, Invalid)
    assert read.message == "No version in here."
    assert "version = 2" in read.details[0]


def test_a_version_that_isnt_a_whole_number_is_invalid():
    for version in ("1", 1.0, True):
        read = repo_settings.parse({"version": version}, "here", Version)
        assert read == Invalid("version in here must be a whole number.", ())


def test_a_version_the_tool_doesnt_read_names_those_it_does():
    read = repo_settings.parse({"version": 3}, "here", Version)
    assert isinstance(read, Invalid)
    assert read.message == "here is version 3, which this tool doesn't read."
    assert "versions 1 and 2" in read.details[0]


def test_text_is_parsed_as_toml():
    read = repo_settings.loads('version = 1\nsite = "x"\n', "here", Version)
    assert read == Settings(Version.V1, {"site": "x"}, "here", None)


def test_text_that_isnt_toml_is_invalid():
    read = repo_settings.loads("version = ", "here", Version)
    assert isinstance(read, Invalid)
    assert read.message == "here isn't valid TOML."


def test_a_file_named_outright_is_read_and_named_in_what_is_wrong(tmp_path: Path):
    path = tmp_path / "settings.toml"
    path.write_text("site = 'x'\n")
    read = repo_settings.read_file(path, Version)
    assert isinstance(read, Invalid)
    assert read.message == f"No version in {path}."


def test_a_file_named_outright_that_isnt_there_is_missing(tmp_path: Path):
    path = tmp_path / "settings.toml"
    assert repo_settings.read_file(path, Version) == Missing(str(path))


def test_settings_read_from_the_copy_they_say_need_no_notice():
    assert repo_settings.notice(Settings(Version.V1, {}, "here", None)) is None


def test_a_copy_that_is_ignored_is_named_with_the_one_used():
    settings = Settings(Version.V1, {}, ".config/ianf-x.toml on main", Path("/wt/.config/x.toml"))
    assert repo_settings.notice(settings) == (
        "Your edits to /wt/.config/x.toml aren't used: .config/ianf-x.toml on main is."
    )
