from __future__ import annotations

import argparse
from typing import Any

from .config import GoogleSheetsConfig, GreenhouseConfig, RedshiftConfig
from .harvest import HarvestClient
from .sinks import GoogleSheetsSink, RedshiftSink


def _parse_filter(values: list[str]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"Invalid filter '{value}'. Expected key=value.")
        key, raw_value = value.split("=", 1)
        parsed[key] = raw_value
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export Greenhouse Harvest v3 data.")
    parser.add_argument("--endpoint", required=True, help="Harvest v3 endpoint, e.g. applications")
    parser.add_argument(
        "--sink",
        required=True,
        choices=["redshift", "sheets"],
        help="Destination for the extracted records",
    )
    parser.add_argument(
        "--table-name",
        help="Redshift table name. Defaults to the endpoint name with slashes replaced by underscores.",
    )
    parser.add_argument(
        "--load-mode",
        choices=["append", "truncate", "upsert"],
        default="append",
        help="Redshift load behavior. Upsert replaces rows by greenhouse_id within an endpoint.",
    )
    parser.add_argument(
        "--worksheet-name",
        help="Google Sheets worksheet name. Defaults to GOOGLE_SHEETS_WORKSHEET.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional max record count for smoke testing",
    )
    parser.add_argument(
        "--filter",
        action="append",
        default=[],
        help="Query filter in key=value form. Repeat for multiple filters.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    greenhouse_config = GreenhouseConfig.from_env()
    client = HarvestClient(greenhouse_config)
    records = client.fetch_endpoint(
        endpoint=args.endpoint,
        params=_parse_filter(args.filter),
        limit=args.limit,
    )
    extracted_at = client.extraction_timestamp()

    if args.sink == "redshift":
        sink = RedshiftSink(RedshiftConfig.from_env())
        table_name = args.table_name or args.endpoint.replace("/", "_")
        sink.write(
            table_name=table_name,
            records=records,
            extracted_at=extracted_at,
            endpoint=args.endpoint,
            load_mode=args.load_mode,
        )
    else:
        sheets_config = GoogleSheetsConfig.from_env()
        sink = GoogleSheetsSink(sheets_config)
        sink.write(
            worksheet_name=args.worksheet_name or sheets_config.worksheet_name,
            records=records,
            extracted_at=extracted_at,
        )

    print(f"Wrote {len(records)} records from '{args.endpoint}' to {args.sink}.")


if __name__ == "__main__":
    main()
