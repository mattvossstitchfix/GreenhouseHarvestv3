from __future__ import annotations

import json
from typing import Any

import gspread
from google.oauth2.service_account import Credentials
import redshift_connector

from .config import GoogleSheetsConfig, RedshiftConfig


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


class RedshiftSink:
    def __init__(self, config: RedshiftConfig) -> None:
        self.config = config

    def _connect(self) -> redshift_connector.Connection:
        return redshift_connector.connect(
            host=self.config.host,
            database=self.config.database,
            user=self.config.user,
            password=self.config.password,
            port=self.config.port,
            iam=self.config.iam,
        )

    def _ensure_base_objects(self, cursor: redshift_connector.Cursor) -> None:
        schema_sql = _quote_identifier(self.config.schema)
        manifest_sql = f"{schema_sql}.{_quote_identifier('_ingestion_manifest')}"
        cursor.execute(f"create schema if not exists {schema_sql}")
        cursor.execute(
            f"""
            create table if not exists {manifest_sql} (
                endpoint varchar(256) encode zstd,
                table_name varchar(256) encode zstd,
                load_mode varchar(32) encode zstd,
                extracted_at timestamptz encode zstd,
                record_count integer encode zstd
            )
            """
        )

    def write(
        self,
        table_name: str,
        records: list[dict[str, Any]],
        extracted_at: str,
        endpoint: str,
        load_mode: str = "append",
    ) -> None:
        if not records:
            return

        schema_sql = _quote_identifier(self.config.schema)
        table_sql = f"{schema_sql}.{_quote_identifier(table_name)}"
        stage_sql = f"{schema_sql}.{_quote_identifier(f'{table_name}__stage')}"
        manifest_sql = f"{schema_sql}.{_quote_identifier('_ingestion_manifest')}"
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._ensure_base_objects(cursor)
                cursor.execute(
                    f"""
                    create table if not exists {table_sql} (
                        greenhouse_id bigint,
                        endpoint varchar(256) encode zstd,
                        extracted_at timestamptz encode zstd,
                        payload super
                    )
                    """
                )
                if load_mode == "truncate":
                    cursor.execute(f"truncate table {table_sql}")
                    insert_target_sql = table_sql
                elif load_mode == "upsert":
                    cursor.execute(f"drop table if exists {stage_sql}")
                    cursor.execute(f"create table {stage_sql} (like {table_sql})")
                    insert_target_sql = stage_sql
                else:
                    insert_target_sql = table_sql

                insert_sql = f"""
                    insert into {insert_target_sql} (greenhouse_id, endpoint, extracted_at, payload)
                    values (%s, %s, %s, json_parse(%s))
                """
                for record in records:
                    cursor.execute(
                        insert_sql,
                        (record.get("id"), endpoint, extracted_at, json.dumps(record, ensure_ascii=True)),
                    )

                if load_mode == "upsert":
                    cursor.execute(
                        f"""
                        delete from {table_sql}
                        using {stage_sql}
                        where {table_sql}.greenhouse_id = {stage_sql}.greenhouse_id
                          and {table_sql}.endpoint = {stage_sql}.endpoint
                        """
                    )
                    cursor.execute(
                        f"""
                        insert into {table_sql} (greenhouse_id, endpoint, extracted_at, payload)
                        select greenhouse_id, endpoint, extracted_at, payload
                        from {stage_sql}
                        """
                    )
                    cursor.execute(f"drop table if exists {stage_sql}")

                cursor.execute(
                    f"""
                    insert into {manifest_sql} (endpoint, table_name, load_mode, extracted_at, record_count)
                    values (%s, %s, %s, %s, %s)
                    """,
                    (endpoint, table_name, load_mode, extracted_at, len(records)),
                )
            connection.commit()
        finally:
            connection.close()


class GoogleSheetsSink:
    def __init__(self, config: GoogleSheetsConfig) -> None:
        self.config = config

    @staticmethod
    def _flatten_value(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, separators=(",", ":"), ensure_ascii=True)
        return str(value)

    def write(self, worksheet_name: str, records: list[dict[str, Any]], extracted_at: str) -> None:
        if not records:
            return

        credentials = Credentials.from_service_account_file(
            self.config.service_account_json,
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ],
        )
        client = gspread.authorize(credentials)
        spreadsheet = client.open_by_key(self.config.spreadsheet_id)
        try:
            worksheet = spreadsheet.worksheet(worksheet_name)
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=26)

        headers = ["extracted_at"]
        for record in records:
            for key in record.keys():
                if key not in headers:
                    headers.append(key)

        rows = [headers]
        for record in records:
            rows.append([extracted_at] + [self._flatten_value(record.get(header)) for header in headers[1:]])

        worksheet.clear()
        worksheet.update(rows, value_input_option="RAW")
