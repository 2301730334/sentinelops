import pytest

from app.errors import ValidationError
from app.services.csv_parser import UnsupportedFileType, check_extension, parse_connections

from .conftest import BENIGN_ROW, HEADER, SCAN_ROW, make_csv


def test_parses_rows_and_missing_values():
    rows = parse_connections(make_csv(), max_rows=10)
    assert rows[0] == {"duration": 4.2, "orig_bytes": 820.0, "resp_bytes": 15400.0,
                       "orig_pkts": 9.0, "resp_pkts": 18.0, "proto": "tcp", "conn_state": "SF"}
    assert rows[1]["duration"] == 0.0 and rows[1]["orig_bytes"] == 0.0


def test_extra_columns_any_order_case_and_bom():
    data = ("﻿TS,uid,Proto,Conn_State,duration,orig_bytes,resp_bytes,orig_pkts,resp_pkts,label\n"
            "1.0,C1,UDP,s0,0.5,10,0,1,0,Malicious\n").encode("utf-8")
    [row] = parse_connections(data, max_rows=10)
    assert row["proto"] == "udp" and row["conn_state"] == "S0" and row["duration"] == 0.5


@pytest.mark.parametrize("delimiter", ["|", "\t", ";"])
def test_delimiter_detection(delimiter):
    data = make_csv(header=HEADER.replace(",", delimiter),
                    rows=[BENIGN_ROW.replace(",", delimiter)])
    assert len(parse_connections(data, max_rows=10)) == 1


def test_blank_lines_skipped():
    assert len(parse_connections(make_csv(rows=[BENIGN_ROW, "", SCAN_ROW]), 10)) == 2


def test_missing_columns():
    with pytest.raises(ValidationError) as exc:
        parse_connections(b"duration,proto\n1,tcp\n", max_rows=10)
    assert "conn_state" in exc.value.details["missing_columns"]
    assert exc.value.status_code == 422


@pytest.mark.parametrize("bad", ["abc", "-5", "inf", "1e999", "0x10"])
def test_invalid_numbers_reported_with_line(bad):
    with pytest.raises(ValidationError) as exc:
        parse_connections(make_csv(rows=[BENIGN_ROW, f"{bad},1,1,1,1,tcp,SF"]), max_rows=10)
    assert exc.value.details["row_errors"][0]["line"] == 3


def test_error_list_is_capped():
    with pytest.raises(ValidationError) as exc:
        parse_connections(make_csv(rows=["x,1,1,1,1,tcp,SF"] * 50), max_rows=100)
    assert len(exc.value.details["errors"]) == 10


def test_short_row_treated_as_missing_values():
    [row] = parse_connections(make_csv(rows=["1.5,100"]), max_rows=10)
    assert row["resp_bytes"] == 0.0 and row["conn_state"] == "-"


@pytest.mark.parametrize("data, message", [
    (b"", "empty"), (b"   \n", "empty"), (HEADER.encode() + b"\n", "no data rows"),
    (b"\x00\x01\x02binary", "binary"), ("é".encode("latin-1") + b"\n1", "UTF-8"),
])
def test_rejects_bad_files(data, message):
    with pytest.raises(ValidationError, match=message):
        parse_connections(data, max_rows=10)


def test_row_limit():
    with pytest.raises(ValidationError, match="more than 2"):
        parse_connections(make_csv(rows=[BENIGN_ROW] * 3), max_rows=2)


@pytest.mark.parametrize("name", ["data.txt", "data.csv.exe", "noext", ""])
def test_extension_check_rejects(name):
    with pytest.raises(UnsupportedFileType):
        check_extension(name)


def test_extension_check_accepts_uppercase():
    check_extension("DATA.CSV")
