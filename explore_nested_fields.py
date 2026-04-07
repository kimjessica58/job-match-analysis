"""Explore nested RECORD REPEATED fields in user_job_match_settings."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import bq_client
import config
import pandas as pd

pd.set_option("display.max_rows", 200)
pd.set_option("display.max_columns", 20)
pd.set_option("display.width", 200)
pd.set_option("display.max_colwidth", 80)

FULL_TABLE = config.FULL_TABLE
DATASET = f"{config.PROJECT_ID}.{config.DATASET}"

# ─── Step 1: Discover all sub-fields for target_* RECORD columns ───
print("=" * 80)
print("STEP 1: Discover sub-fields via INFORMATION_SCHEMA.COLUMN_FIELD_PATHS")
print("=" * 80)

schema_sql = f"""
SELECT column_name, field_path, data_type
FROM `{DATASET}.INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`
WHERE table_name = 'user_job_match_settings'
  AND column_name LIKE 'target_%'
ORDER BY column_name, field_path
"""
schema_df = bq_client.run_query(schema_sql)
print(schema_df.to_string(index=False))
print()

# ─── Step 2a: target_locations — distinct (city, state) pairs ───
print("=" * 80)
print("STEP 2a: target_locations — distinct (city, state) pairs (limit 50)")
print("=" * 80)

loc_sql = f"""
SELECT DISTINCT loc.city, loc.state
FROM `{FULL_TABLE}`,
UNNEST(target_locations) AS loc
WHERE loc.city IS NOT NULL AND loc.city != ''
ORDER BY loc.state, loc.city
LIMIT 50
"""
loc_df = bq_client.run_query(loc_sql)
print(loc_df.to_string(index=False))
print(f"\nTotal rows returned: {len(loc_df)}")
print()

# ─── Helper: for each RECORD column, get distinct values of STRING sub-fields ───
def explore_record_column(column_name, schema_df):
    """For a given RECORD column, find its STRING sub-fields and query distinct values."""
    # Filter schema to this column's sub-fields (exclude the top-level RECORD row itself)
    col_fields = schema_df[
        (schema_df["column_name"] == column_name) &
        (schema_df["field_path"] != column_name)
    ].copy()

    if col_fields.empty:
        print(f"  No sub-fields found for {column_name}")
        return

    print(f"  Sub-fields:")
    for _, row in col_fields.iterrows():
        print(f"    {row['field_path']}  ({row['data_type']})")
    print()

    # Query distinct values for STRING sub-fields (skip id/uuid-looking fields)
    for _, row in col_fields.iterrows():
        fp = row["field_path"]
        dt = row["data_type"]
        sub_field = fp.split(".")[-1]

        # Skip non-string fields and id/uuid fields
        if "STRING" not in dt:
            continue
        if sub_field.lower() in ("id", "uuid", "ref_id", "reference_id"):
            continue

        alias = column_name.replace("target_", "t_")[:10]
        sql = f"""
SELECT DISTINCT {alias}.{sub_field} AS value
FROM `{FULL_TABLE}`,
UNNEST({column_name}) AS {alias}
WHERE {alias}.{sub_field} IS NOT NULL AND {alias}.{sub_field} != ''
ORDER BY value
LIMIT 50
"""
        try:
            df = bq_client.run_query(sql)
            print(f"  Distinct {fp} ({len(df)} values):")
            for v in df["value"].tolist():
                print(f"    - {v}")
            print()
        except Exception as e:
            print(f"  Error querying {fp}: {e}")
            print()


# ─── Steps 2b-2h: Explore each RECORD column ───
record_columns = [
    "target_industries",
    "target_transit_lines",
    "target_neighborhoods",
    "target_certifications",
    "target_roles_ref",
    "target_role_class",
    "target_education_fields",
]

for i, col in enumerate(record_columns):
    label = chr(ord("b") + i)
    print("=" * 80)
    print(f"STEP 2{label}: {col}")
    print("=" * 80)
    explore_record_column(col, schema_df)
