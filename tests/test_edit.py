from enum import IntEnum

import repo_settings
from repo_settings import Assignment, Invalid, NewFile

SCHEMA = "https://example.org/schema/ianf-thing.v1.json"


class Version(IntEnum):
    V1 = 1


NEW = NewFile(Version.V1, SCHEMA)


def edit(text: str | None, *assignments: Assignment) -> str | Invalid:
    return repo_settings.edit(text, "here", NEW, assignments)


def test_a_missing_file_is_created_with_its_schema_version_and_the_key():
    assert edit(None, Assignment((), "colour", "red")) == (
        f'#:schema {SCHEMA}\nversion = 1\ncolour = "red"\n'
    )


def test_a_missing_file_gets_the_table_its_key_is_in():
    assert edit(None, Assignment(("jira",), "space", "APP")) == (
        f'#:schema {SCHEMA}\nversion = 1\n\n[jira]\nspace = "APP"\n'
    )


def test_a_keys_value_is_changed_keeping_the_rest_of_the_file_as_it_was():
    text = '#:schema x\nversion = 1\n# How it looks\ncolour = "red"  # for now\nsize = 2\n'
    assert edit(text, Assignment((), "colour", "blue")) == (
        '#:schema x\nversion = 1\n# How it looks\ncolour = "blue"  # for now\nsize = 2\n'
    )


def test_a_missing_key_is_added_to_its_table():
    text = 'version = 1\n\n[jira]\nsite = "x"\n'
    assert edit(text, Assignment(("jira",), "space", "APP")) == (
        'version = 1\n\n[jira]\nsite = "x"\nspace = "APP"\n'
    )


def test_a_missing_top_level_key_goes_above_the_tables():
    text = 'version = 1\n\n[jira]\nsite = "x"\n'
    assert edit(text, Assignment((), "colour", "red")) == (
        'version = 1\ncolour = "red"\n\n[jira]\nsite = "x"\n'
    )


def test_a_missing_table_is_created():
    text = 'version = 1\n\n[jira]\nsite = "x"\n'
    assert edit(text, Assignment(("map",), "out", "docs")) == (
        'version = 1\n\n[jira]\nsite = "x"\n\n[map]\nout = "docs"\n'
    )


def test_a_table_is_created_inside_another():
    text = 'version = 1\n\n[jira]\nsite = "x"\n'
    assert edit(text, Assignment(("jira", "fields"), "points", "cf_1")) == (
        'version = 1\n\n[jira]\nsite = "x"\n\n[jira.fields]\npoints = "cf_1"\n'
    )


def test_a_key_in_a_table_written_with_dotted_keys_is_added_the_same_way():
    assert edit("version = 1\na.b = 1\n", Assignment(("a",), "c", 2)) == (
        "version = 1\na.b = 1\na.c = 2\n"
    )


def test_assignments_are_made_in_order():
    assert edit(
        "version = 1\n", Assignment((), "colour", "red"), Assignment((), "colour", "blue")
    ) == ('version = 1\ncolour = "blue"\n')


def test_setting_the_value_a_key_already_has_leaves_the_text_exactly_as_it_was():
    text = 'version = 1\ncolour   =   "red"\n'
    assert edit(text, Assignment((), "colour", "red")) == text


def test_a_table_name_that_holds_a_value_is_invalid():
    assert edit("version = 1\njira = 3\n", Assignment(("jira",), "space", "APP")) == Invalid(
        "jira in here isn't a table, so space can't be set in it.", ()
    )


def test_a_file_that_isnt_valid_toml_is_invalid():
    read = edit("version = \n", Assignment((), "colour", "red"))
    assert isinstance(read, Invalid)
    assert read.message == "here isn't valid TOML."


def test_a_file_in_a_version_the_tool_doesnt_read_is_invalid():
    read = edit("version = 9\n", Assignment((), "colour", "red"))
    assert isinstance(read, Invalid)
    assert read.message == "here is version 9, which this tool doesn't read."


def test_a_file_without_a_version_is_invalid_rather_than_given_one():
    read = edit('colour = "red"\n', Assignment((), "colour", "blue"))
    assert isinstance(read, Invalid)
    assert read.message == "No version in here."
