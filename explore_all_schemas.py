"""
Comprehensive schema exploration for all 6 BigQuery tables.
Queries INFORMATION_SCHEMA, gets nested field paths, and samples categorical values.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import bq_client
import config

PROJECT = config.PROJECT_ID
DATASET = config.DATASET

TABLES = [
    "job_postings",
    "user",
    "user_job_match_auto_apply_posting",
    "user_job_match_auto_apply_posting_match",
    "user_job_match_settings",
    "xml_job_feed_raw_jobs",
]

# Column name substrings that indicate non-categorical (skip for distinct values)
SKIP_KEYWORDS = [
    "id", "uuid", "url", "link", "token", "key", "password", "hash", "salt",
    "image", "photo", "avatar", "resume", "description", "note", "comment",
    "body", "text", "content", "summary", "bio", "headline", "raw", "html",
    "json", "xml", "payload", "data", "metadata", "response", "request",
]

# Sub-field names worth sampling in RECORD REPEATED fields
CATEGORICAL_SUBFIELD_NAMES = [
    "name", "alias", "type", "status", "level", "category", "kind", "role",
    "state", "country", "city", "label", "code", "source", "mode", "tier",
    "grade", "rank", "class", "group", "tag", "format", "method", "protocol",
    "currency", "language", "locale", "region", "zone", "area", "sector",
    "industry", "department", "division", "unit", "team", "title", "position",
    "employment_type", "job_type", "work_type", "schedule_type", "shift",
    "experience_level", "education_level", "degree", "certification",
    "remote", "hybrid", "onsite", "is_remote",
]

# Sub-field names to skip in RECORD fields
SKIP_SUBFIELD_KEYWORDS = [
    "uuid", "id", "lat", "long", "longitude", "latitude",
    "street", "zipcode", "zip_code", "zip", "address",
    "url", "link", "token", "key", "password", "hash",
    "image", "photo", "avatar", "description", "note",
    "body", "text", "content", "summary", "raw", "html",
    "json", "xml", "payload", "metadata", "response", "request",
    "created_at", "updated_at", "deleted_at", "timestamp",
]


def should_skip_column(col_name):
    """Check if column name contains any skip keyword."""
    col_lower = col_name.lower()
    for kw in SKIP_KEYWORDS:
        if kw in col_lower:
            return True, kw
    return False, None


def should_skip_subfield(field_name):
    """Check if a sub-field name should be skipped."""
    field_lower = field_name.lower()
    for kw in SKIP_SUBFIELD_KEYWORDS:
        if kw == field_lower or field_lower.endswith(f"_{kw}") or field_lower.startswith(f"{kw}_"):
            return True
    return False


def get_skip_reason(col_name):
    """Return a human-readable skip reason."""
    col_lower = col_name.lower()
    reasons = {
        "id": "identifier field", "uuid": "unique identifier",
        "url": "URL field", "link": "URL/link field",
        "token": "token/auth field", "key": "key field",
        "password": "sensitive credential", "hash": "hash value",
        "salt": "crypto salt", "image": "image reference",
        "photo": "photo reference", "avatar": "avatar reference",
        "resume": "document/file content", "description": "free-text description",
        "note": "free-text notes", "comment": "free-text comments",
        "body": "free-text body", "text": "free-text field",
        "content": "free-text content", "summary": "free-text summary",
        "bio": "free-text biography", "headline": "free-text headline",
        "raw": "raw data blob", "html": "HTML content",
        "json": "JSON blob", "xml": "XML content",
        "payload": "data payload", "data": "generic data field",
        "metadata": "metadata blob", "response": "response payload",
        "request": "request payload",
    }
    for kw, reason in reasons.items():
        if kw in col_lower:
            return reason
    return "skipped"


def main():
    full_table_ref = lambda t: f"`{PROJECT}.{DATASET}.{t}`"

    # ── Step 1: Get schemas and field paths for all tables in batch ──
    print("=" * 100)
    print("STEP 1: Fetching schemas and field paths for all 6 tables...")
    print("=" * 100)

    # Query 1: All columns for all tables
    table_list = ", ".join([f"'{t}'" for t in TABLES])
    schema_sql = f"""
    SELECT table_name, column_name, data_type, is_nullable, ordinal_position
    FROM `{PROJECT}.{DATASET}.INFORMATION_SCHEMA.COLUMNS`
    WHERE table_name IN ({table_list})
    ORDER BY table_name, ordinal_position
    """

    # Query 2: All field paths for all tables (nested fields)
    fields_sql = f"""
    SELECT table_name, column_name, field_path, data_type, description
    FROM `{PROJECT}.{DATASET}.INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`
    WHERE table_name IN ({table_list})
    ORDER BY table_name, column_name, field_path
    """

    print("\nFetching INFORMATION_SCHEMA.COLUMNS ...")
    schema_df = bq_client.run_query(schema_sql)
    print(f"  Got {len(schema_df)} column records")

    print("Fetching INFORMATION_SCHEMA.COLUMN_FIELD_PATHS ...")
    fields_df = bq_client.run_query(fields_sql)
    print(f"  Got {len(fields_df)} field path records")

    # ── Step 2: Identify categorical columns and build batch queries ──
    print("\n" + "=" * 100)
    print("STEP 2: Identifying categorical columns and querying distinct values...")
    print("=" * 100)

    # Organize data by table
    for table_name in TABLES:
        print(f"\n{'#' * 100}")
        print(f"# TABLE: {table_name}")
        print(f"{'#' * 100}")

        table_schema = schema_df[schema_df["table_name"] == table_name].copy()
        table_fields = fields_df[fields_df["table_name"] == table_name].copy()
        full_ref = full_table_ref(table_name)

        if table_schema.empty:
            print("  ** No schema found - table may not exist **")
            continue

        # Print full schema
        print(f"\n  SCHEMA ({len(table_schema)} columns):")
        print(f"  {'Column Name':<50} {'Data Type':<40} {'Nullable'}")
        print(f"  {'-'*50} {'-'*40} {'-'*8}")
        for _, row in table_schema.iterrows():
            print(f"  {row['column_name']:<50} {row['data_type']:<40} {row['is_nullable']}")

        # Print nested field paths (only show sub-fields, not top-level duplicates)
        nested = table_fields[table_fields["field_path"] != table_fields["column_name"]]
        if not nested.empty:
            print(f"\n  NESTED FIELD PATHS ({len(nested)} sub-fields):")
            print(f"  {'Column':<30} {'Field Path':<50} {'Data Type':<30}")
            print(f"  {'-'*30} {'-'*50} {'-'*30}")
            for _, row in nested.iterrows():
                print(f"  {row['column_name']:<30} {row['field_path']:<50} {row['data_type']:<30}")

        # ── Step 3: Query categorical values ──
        print(f"\n  CATEGORICAL VALUES:")

        # Identify RECORD/REPEATED columns and their sub-fields
        record_columns = {}
        for _, row in table_schema.iterrows():
            dtype = row["data_type"]
            cname = row["column_name"]
            if "STRUCT" in dtype or "RECORD" in dtype:
                # Get sub-fields for this column
                sub = table_fields[
                    (table_fields["column_name"] == cname) &
                    (table_fields["field_path"] != cname)
                ]
                record_columns[cname] = sub

        # Process each column
        for _, row in table_schema.iterrows():
            col = row["column_name"]
            dtype = row["data_type"]
            skip, keyword = should_skip_column(col)

            print(f"\n    Column: {col}")
            print(f"    Type:   {dtype}")

            if col in record_columns:
                # Handle RECORD/REPEATED fields
                sub_fields = record_columns[col]
                is_repeated = "ARRAY" in dtype or "REPEATED" in dtype
                print(f"    [RECORD {'REPEATED' if is_repeated else 'NULLABLE'}]")

                if sub_fields.empty:
                    print(f"      (no sub-fields found)")
                    continue

                for _, sf in sub_fields.iterrows():
                    sf_name = sf["field_path"].split(".")[-1]
                    sf_path = sf["field_path"]
                    sf_type = sf["data_type"]

                    if should_skip_subfield(sf_name):
                        print(f"      Sub-field: {sf_path} ({sf_type}) - skipped (likely {sf_name})")
                        continue

                    if sf_type not in ("STRING", "BOOL", "BOOLEAN", "INT64", "FLOAT64", "NUMERIC"):
                        print(f"      Sub-field: {sf_path} ({sf_type}) - skipped (complex type)")
                        continue

                    # Query distinct values from unnested field
                    try:
                        if is_repeated:
                            count_sql = f"""
                            SELECT COUNT(DISTINCT sub.{sf_name}) as cnt
                            FROM {full_ref}, UNNEST({col}) AS sub
                            WHERE sub.{sf_name} IS NOT NULL
                            """
                            vals_sql = f"""
                            SELECT DISTINCT CAST(sub.{sf_name} AS STRING) as val
                            FROM {full_ref}, UNNEST({col}) AS sub
                            WHERE sub.{sf_name} IS NOT NULL
                            ORDER BY val
                            LIMIT 50
                            """
                        else:
                            count_sql = f"""
                            SELECT COUNT(DISTINCT {sf_path}) as cnt
                            FROM {full_ref}
                            WHERE {sf_path} IS NOT NULL
                            """
                            vals_sql = f"""
                            SELECT DISTINCT CAST({sf_path} AS STRING) as val
                            FROM {full_ref}
                            WHERE {sf_path} IS NOT NULL
                            ORDER BY val
                            LIMIT 50
                            """
                        count_df = bq_client.run_query(count_sql)
                        cnt = int(count_df["cnt"].iloc[0])
                        vals_df = bq_client.run_query(vals_sql)
                        vals = vals_df["val"].tolist()

                        if cnt <= 30:
                            print(f"      Sub-field: {sf_path} ({sf_type}) - {cnt} unique values:")
                            for v in vals:
                                print(f"        - {v}")
                        else:
                            print(f"      Sub-field: {sf_path} ({sf_type}) - {cnt} unique values (showing 50):")
                            for v in vals[:50]:
                                print(f"        - {v}")
                    except Exception as e:
                        print(f"      Sub-field: {sf_path} ({sf_type}) - ERROR: {e}")

            elif skip:
                reason = get_skip_reason(col)
                print(f"    -> SKIPPED - {reason}")

            elif dtype in ("STRING", "BOOL", "BOOLEAN"):
                # Query distinct values
                try:
                    count_sql = f"""
                    SELECT COUNT(DISTINCT `{col}`) as cnt
                    FROM {full_ref}
                    WHERE `{col}` IS NOT NULL
                    """
                    vals_sql = f"""
                    SELECT DISTINCT CAST(`{col}` AS STRING) as val
                    FROM {full_ref}
                    WHERE `{col}` IS NOT NULL
                    ORDER BY val
                    LIMIT 50
                    """
                    count_df = bq_client.run_query(count_sql)
                    cnt = int(count_df["cnt"].iloc[0])
                    vals_df = bq_client.run_query(vals_sql)
                    vals = vals_df["val"].tolist()

                    if cnt <= 30:
                        print(f"    -> {cnt} unique values:")
                        for v in vals:
                            print(f"        - {v}")
                    else:
                        print(f"    -> {cnt} unique values (showing first 50):")
                        for v in vals[:50]:
                            print(f"        - {v}")
                except Exception as e:
                    print(f"    -> ERROR querying values: {e}")

            elif dtype in ("INT64", "FLOAT64", "NUMERIC", "BIGNUMERIC"):
                print(f"    -> numeric column (not sampled for distinct values)")

            elif "TIMESTAMP" in dtype or "DATE" in dtype or "TIME" in dtype:
                print(f"    -> temporal column (not sampled)")

            elif "BYTES" in dtype:
                print(f"    -> binary column (not sampled)")

            else:
                print(f"    -> type '{dtype}' not sampled")

    print("\n" + "=" * 100)
    print("DONE - Schema exploration complete.")
    print("=" * 100)


if __name__ == "__main__":
    main()
