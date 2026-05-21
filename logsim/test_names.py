"""Test the names module.

Used in the Logic Simulator project to comprehensively test the Names class.
"""

import pytest

from names import Names


@pytest.fixture
def names():
    """Return a fresh instance of the Names class for each test."""
    return Names()


def test_initialization(names):
    """Test the initial state of the Names instance."""
    assert names.error_code_count == 0
    assert names.names == []
    assert names._name_to_id == {}


def test_unique_error_codes_valid(names):
    """Test allocation of unique error codes with valid positive integers."""
    codes_1 = names.unique_error_codes(3)
    assert codes_1 == range(0, 3)
    assert names.error_code_count == 3

    codes_2 = names.unique_error_codes(5)
    assert codes_2 == range(3, 8)
    assert names.error_code_count == 8


@pytest.mark.parametrize("invalid_val", [0, -1, -50])
def test_unique_error_codes_invalid_value(names, invalid_val):
    """Test that zero or negative values raise a ValueError."""
    with pytest.raises(
        ValueError, match="Expected num_error_codes to be a positive integer."
    ):
        names.unique_error_codes(invalid_val)


@pytest.mark.parametrize("invalid_type", [3.14, "3", [3], None])
def test_unique_error_codes_invalid_type(names, invalid_type):
    """Test that non-integer types raise a ValueError."""
    with pytest.raises(
        ValueError, match="Expected num_error_codes to be a positive integer."
    ):
        names.unique_error_codes(invalid_type)


def test_lookup_valid_new_strings(names):
    """Test lookup functionality with previously unseen strings."""
    string_list = ["alpha", "beta", "gamma"]
    ids = names.lookup(string_list)

    assert ids == [0, 1, 2]
    assert names.names == string_list
    assert names._name_to_id == {"alpha": 0, "beta": 1, "gamma": 2}


def test_lookup_existing_strings(names):
    """Test lookup functionality with already registered strings."""
    names.lookup(["alpha", "beta"])
    ids = names.lookup(["beta", "alpha", "beta"])

    assert ids == [1, 0, 1]
    assert len(names.names) == 2  # Ensures no duplicates were added


def test_lookup_mixed_strings(names):
    """Test lookup functionality with a mix of new and existing strings."""
    names.lookup(["alpha", "beta"])
    ids = names.lookup(["beta", "gamma", "alpha", "delta"])

    assert ids == [1, 2, 0, 3]
    assert names.names == ["alpha", "beta", "gamma", "delta"]


def test_lookup_empty_iterable(names):
    """Test lookup functionality handles an empty iterable correctly."""
    ids = names.lookup([])
    assert ids == []
    assert names.names == []
    assert names._name_to_id == {}


def test_lookup_and_query_empty_string(names):
    """Test that an empty string is treated as a valid unique name."""
    ids = names.lookup([""])
    assert ids == [0]
    assert names.query("") == 0
    assert names.get_name_string(0) == ""


@pytest.mark.parametrize("invalid_iterable", ["string_itself", b"bytes", 123, None])
def test_lookup_invalid_iterable_type(names, invalid_iterable):
    """Test that strings, bytes, or non-iterables raise a TypeError."""
    with pytest.raises(TypeError, match="Expected an iterable collection"):
        names.lookup(invalid_iterable)


def test_lookup_invalid_element_type(names):
    """Test that iterables containing non-string elements raise a TypeError."""
    with pytest.raises(TypeError, match="Iterable must contain only strings"):
        names.lookup(["valid", 123, "also_valid"])


def test_query_existing_string(names):
    """Test querying a string that is already in the dictionary."""
    names.lookup(["alpha", "beta"])
    assert names.query("beta") == 1
    assert names.query("alpha") == 0


def test_query_missing_string(names):
    """Test querying a string that does not exist in the dictionary."""
    names.lookup(["alpha", "beta"])
    assert names.query("gamma") is None


@pytest.mark.parametrize("invalid_type", [1, ["alpha"], None, 3.14])
def test_query_invalid_type(names, invalid_type):
    """Test that querying with non-string inputs raises a TypeError."""
    with pytest.raises(TypeError, match="Expected name_string to be a string."):
        names.query(invalid_type)


def test_get_name_string_valid_id(names):
    """Test retrieving strings using valid IDs."""
    names.lookup(["alpha", "beta", "gamma"])
    assert names.get_name_string(0) == "alpha"
    assert names.get_name_string(2) == "gamma"


@pytest.mark.parametrize("invalid_id", [-1, 3, 100])
def test_get_name_string_invalid_id_bounds(names, invalid_id):
    """Test retrieving strings with out-of-bounds IDs returns None."""
    names.lookup(["alpha", "beta", "gamma"])
    assert names.get_name_string(invalid_id) is None


@pytest.mark.parametrize("invalid_type", ["1", 1.0, [1], None])
def test_get_name_string_invalid_type(names, invalid_type):
    """Test that retrieving strings with non-integer inputs raises a TypeError."""
    with pytest.raises(TypeError, match="Expected name_id to be an integer."):
        names.get_name_string(invalid_type)


def test_stress_lookup(names):
    """Test looking up and retrieving a large volume of names efficiently."""
    large_list = [f"name_{i}" for i in range(10000)]
    ids = names.lookup(large_list)

    # Check length and specific boundary values
    assert len(ids) == 10000
    assert ids[0] == 0
    assert ids[-1] == 9999

    # Check that retrieving the last item works as expected
    assert names.query("name_9999") == 9999
    assert names.get_name_string(9999) == "name_9999"
