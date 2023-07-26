import math
from datetime import datetime
from itertools import chain, product, repeat

import pytest

import tenere.main
from tenere.main import FuelingInputModel

TEST_TEXT_INPUTS = ["1", "2 ", " 3  ", "4,4", "5.5", "6,6 ", "7.7 "]
TEST_EXPECTED_VALUES = [1, 2, 3, 4.4, 5.5, 6.6, 7.7]
TEST_SUFFIXES = ["km", "KM", "kM", "Km", "e", "E", "€", "l", "L"]
TEST_SUFFIX_REGEXES = ["km"] * 4 + ["[eE€]"] * 3 + ["[lL]"] * 2

TEST_CORRECT_INPUT_TUPLES = [
    list(chain(a, b))
    for a, b in product(
        zip(TEST_TEXT_INPUTS, TEST_EXPECTED_VALUES, strict=True),
        zip(TEST_SUFFIXES, TEST_SUFFIX_REGEXES, strict=True),
    )
]
TEST_NAN_INPUT_TUPLES = [
    list((a, *b))
    for a, b in product(
        TEST_TEXT_INPUTS,
        zip(repeat("foo"), TEST_SUFFIX_REGEXES, strict=False),
    )
]


class TestParsing:
    @pytest.mark.parametrize(
        "test_input,expected",
        [
            ("1", 1.0),
            ("2,2", 2.2),
            ("3.3", 3.3),
            ("  4.4", 4.4),
            ("5.5   ", 5.5),
            ("   6.6   ", 6.6),
            ("   -7.7   ", -7.7),
        ],
    )
    def test_to_float(self, test_input: str, expected: float) -> None:
        assert tenere.main.to_float(test_input) == expected

    @pytest.mark.parametrize(
        "test_input",
        ["", "koira", "- 2", "+++", "1..2", "3,,4", "9koira", "koira8"],
    )
    def test_to_float_returns_nan(self, test_input: str) -> None:
        assert math.isnan(tenere.main.to_float(test_input))

    @pytest.mark.parametrize(
        "test_input,expected,suffix,suffix_regex", TEST_CORRECT_INPUT_TUPLES
    )
    def test_filter_suffixed_value(
        self, test_input: str, suffix: str, suffix_regex: str, expected: float
    ) -> None:
        """
        Test that filter_suffixed_value() return correct value.
        """
        assert (
            tenere.main.filter_suffixed_value(test_input + suffix, suffix_regex)
            == expected
        )

    @pytest.mark.parametrize("test_input,suffix,suffix_regex", TEST_NAN_INPUT_TUPLES)
    def test_filter_suffixed_value_returns_nan(
        self, test_input: str, suffix: str, suffix_regex: str
    ) -> None:
        """
        Test that filter_suffixed_value() returns nan for invalid values.
        """
        assert math.isnan(
            tenere.main.filter_suffixed_value(test_input + suffix, suffix_regex)
        )

    @pytest.mark.parametrize(
        "test_input,expected",
        [
            ("1.1.2023 18:30", datetime.fromisoformat("2023-01-01T18:30+02:00")),
            (" 1.01.2023  18:30 ", datetime.fromisoformat("2023-01-01T18:30+02:00")),
            ("01.1.2023 18.30", datetime.fromisoformat("2023-01-01T18:30+02:00")),
            (
                "foo 01.01.2023   18:30 bar",
                datetime.fromisoformat("2023-01-01T18:30+02:00"),
            ),
            ("01.07.2023 18:30", datetime.fromisoformat("2023-07-01T18:30+03:00")),
            ("01.01.2023", datetime.fromisoformat("2023-01-01T00:00+02:00")),
            ("01.07.2023", datetime.fromisoformat("2023-07-01T00:00+03:00")),
        ],
    )
    def test_filter_datetime(self, test_input, expected):
        """
        Test that filter_datetime() returns correct datetime.
        """
        assert tenere.main.filter_datetime(test_input) == expected

    @pytest.mark.parametrize(
        "test_input",
        [
            "",
            "foo",
            "0.5.2023 18:30",
            "7.13.2023 18:30",
            "1.foo.2023 18:30",
            "33.12.2023",
        ],
    )
    def test_filter_datetime_returns_none(self, test_input):
        """
        Test that filter_datetime() returns None for invalid values.
        """
        assert tenere.main.filter_datetime(test_input) is None


class TestFuelingInputModel:
    @pytest.mark.parametrize(
        "test_input,expected",
        [
            (
                "1.1.2023 10L 1000km 15€",
                FuelingInputModel(
                    date="2023-01-01T00:00+02:00",
                    fuel_litres=10.0,
                    distance_km=1000.0,
                    cost_euros=15.0,
                ),
            ),
            (
                "10 l 1000 km 15   euroo 1.1.2023",
                FuelingInputModel(
                    date="2023-01-01T00:00+02:00",
                    fuel_litres=10.0,
                    distance_km=1000.0,
                    cost_euros=15.0,
                ),
            ),
            (
                "10,2 litraa 1000.222 km 1.1.2023   18:00 15,5E",
                FuelingInputModel(
                    date="2023-01-01T18:00+02:00",
                    fuel_litres=10.2,
                    distance_km=1000.222,
                    cost_euros=15.5,
                ),
            ),
        ],
    )
    def test_fueling_input_model(self, test_input, expected):
        default_date = datetime(2022, 12, 1)
        assert (
            FuelingInputModel.from_text(test_input, default_date=default_date)
            == expected
        )

    @pytest.mark.parametrize(
        "test_input,expected",
        [
            (
                FuelingInputModel(
                    date="2023-01-01T00:00+02:00",
                    fuel_litres=10.0,
                    distance_km=1000.0,
                    cost_euros=15.0,
                ),
                True,
            ),
            (
                FuelingInputModel(
                    date="2023-01-01T00:00+02:00",
                    fuel_litres=float("nan"),
                    distance_km=float("nan"),
                    cost_euros=float("nan"),
                ),
                False,
            ),
        ],
    )
    def test_fueling_input_model_bool(self, test_input, expected: bool):
        assert bool(test_input) == expected
