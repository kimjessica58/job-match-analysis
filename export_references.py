"""Export reference CSVs from BigQuery for the Job Match Analysis project."""

import os
import sys
import re
import pandas as pd

# Add project dir to path so we can import our modules
PROJECT_DIR = "/Users/jessicakim/Documents/Job Match Analysis"
sys.path.insert(0, PROJECT_DIR)

import bq_client
import config

OUTPUT_DIR = os.path.join(PROJECT_DIR, "reference")
os.makedirs(OUTPUT_DIR, exist_ok=True)

DATASET_FULL = f"{config.PROJECT_ID}.{config.DATASET}"

ALL_TABLES = [
    "job_postings",
    "user",
    "user_job_match_auto_apply_posting",
    "user_job_match_auto_apply_posting_match",
    "user_job_match_settings",
    "xml_job_feed_raw_jobs",
]

# ---------- Classification helpers ----------

ID_PATTERNS = re.compile(
    r"(^id$|_id$|^uuid$|_uuid|_key$|_token$|_hash$|_salt$|^key$|^token$|^hash$|^salt$)",
    re.IGNORECASE,
)
URL_PATTERNS = re.compile(
    r"(url|link|image|photo|avatar|resume|logo|picture|href)", re.IGNORECASE
)
TEXT_PATTERNS = re.compile(
    r"(description|note|comment|body|text|content|summary|bio|headline|raw|html|json|xml|payload|snippet|excerpt)",
    re.IGNORECASE,
)
PII_PATTERNS = re.compile(
    r"(^name$|^first_name$|^last_name$|^email$|^phone$|^address$|^street$|display_name|full_name)",
    re.IGNORECASE,
)
TIMESTAMP_PATTERNS = re.compile(
    r"(created_at|updated_at|deleted_at|_date|expired|_at$|timestamp|posted_at|applied_at|last_login|signed_up)",
    re.IGNORECASE,
)
NUMERIC_PATTERNS = re.compile(
    r"(pay_min|pay_max|cpa|score|lat|long|longitude|latitude|salary|compensation|amount|count|total|rating|rank|distance|radius|experience_years|years)",
    re.IGNORECASE,
)


def classify_column(col_name, data_type, table_name):
    """Return (category, needs_distinct_query) tuple."""
    dt = data_type.upper()

    if "ARRAY" in dt:
        return "array", False
    if dt.startswith("STRUCT") or dt == "RECORD":
        return "nested_record", False
    if dt in ("BOOL", "BOOLEAN"):
        return "boolean", False
    if dt in ("TIMESTAMP", "DATETIME", "DATE", "TIME"):
        return "timestamp", False
    if TIMESTAMP_PATTERNS.search(col_name):
        return "timestamp", False

    if ID_PATTERNS.search(col_name):
        return "id_reference", False

    if dt in ("INT64", "FLOAT64", "NUMERIC", "BIGNUMERIC", "INT", "FLOAT", "INTEGER"):
        return "numeric", False
    if NUMERIC_PATTERNS.search(col_name):
        return "numeric", False

    if URL_PATTERNS.search(col_name):
        return "free_text", False
    if TEXT_PATTERNS.search(col_name):
        return "free_text", False
    if PII_PATTERNS.search(col_name):
        return "free_text", False

    # STRING that didn't match known patterns — need to query distinct count
    if "STRING" in dt or dt == "BYTES":
        return None, True  # needs query

    return "free_text", False


def describe_column(category, col_name, data_type):
    """Generate a description based on category and name."""
    if category == "boolean":
        return "TRUE | FALSE"
    if category == "id_reference":
        return "Foreign key / primary key"
    if category == "timestamp":
        return "Timestamp"
    if category == "numeric":
        # Try to give a nicer description
        lower = col_name.lower()
        if "pay" in lower or "salary" in lower or "compensation" in lower:
            return "Compensation amount"
        if "score" in lower:
            return "Score value"
        if "lat" in lower:
            return "Latitude coordinate"
        if "long" in lower:
            return "Longitude coordinate"
        if "cpa" in lower:
            return "Cost per application"
        if "radius" in lower:
            return "Search radius"
        if "experience" in lower or "years" in lower:
            return "Years of experience"
        if "count" in lower or "total" in lower:
            return "Count/total"
        return f"Numeric ({col_name})"
    if category == "nested_record":
        return "Nested RECORD structure"
    if category == "array":
        return "Repeated/array field"
    if category == "free_text":
        lower = col_name.lower()
        if "url" in lower or "link" in lower:
            return "URL"
        if "image" in lower or "photo" in lower or "avatar" in lower or "logo" in lower:
            return "Image URL"
        if "resume" in lower:
            return "Resume file reference"
        if "email" in lower:
            return "Email address"
        if "phone" in lower:
            return "Phone number"
        if "description" in lower:
            return "Free text description"
        if "html" in lower or "xml" in lower:
            return "Markup content"
        if "json" in lower or "payload" in lower or "raw" in lower:
            return "Serialized data"
        if "name" in lower:
            return "Name (text)"
        return f"Free text ({col_name})"
    return col_name


# ---------- File 1: field_reference.csv ----------

def build_field_reference():
    print("=== Building field_reference.csv ===")
    rows = []

    for table in ALL_TABLES:
        print(f"  Fetching schema for {table}...")
        schema_df = bq_client.get_table_schema(table)

        for _, row in schema_df.iterrows():
            col_name = row["column_name"]
            data_type = row["data_type"]

            category, needs_query = classify_column(col_name, data_type, table)

            unique_count = None
            description = None

            if needs_query:
                # Query distinct count
                full_table = f"{DATASET_FULL}.{table}"
                try:
                    sql = f"SELECT COUNT(DISTINCT `{col_name}`) as cnt FROM `{full_table}` WHERE `{col_name}` IS NOT NULL"
                    cnt_df = bq_client.run_query(sql)
                    unique_count = int(cnt_df["cnt"].iloc[0])

                    if unique_count == 0:
                        category = "empty"
                        description = "No non-null values"
                    elif unique_count <= 50:
                        category = "categorical"
                        # Fetch actual values
                        sql2 = f"SELECT DISTINCT `{col_name}` FROM `{full_table}` WHERE `{col_name}` IS NOT NULL ORDER BY `{col_name}` LIMIT 50"
                        vals_df = bq_client.run_query(sql2)
                        vals = vals_df.iloc[:, 0].astype(str).tolist()
                        description = " | ".join(vals)
                    else:
                        category = "free_text"
                        description = f"{unique_count} unique values"
                except Exception as e:
                    category = "free_text"
                    description = f"Error querying: {e}"
            else:
                # For categorical boolean, get counts
                if category == "boolean":
                    unique_count = 2
                    description = "TRUE | FALSE"
                elif category == "timestamp":
                    description = "Timestamp"
                elif category == "id_reference":
                    description = "Foreign key / primary key"
                else:
                    description = describe_column(category, col_name, data_type)

            rows.append({
                "table_name": table,
                "column_name": col_name,
                "data_type": data_type,
                "category": category,
                "unique_count": unique_count if unique_count is not None else "",
                "unique_values_or_description": description,
            })

        print(f"    Done: {len(schema_df)} columns")

    df = pd.DataFrame(rows)
    path = os.path.join(OUTPUT_DIR, "field_reference.csv")
    df.to_csv(path, index=False)
    print(f"  Saved {path} ({os.path.getsize(path):,} bytes, {len(df)} rows)")
    return df


# ---------- Files 2-9: Simple query exports ----------

SIMPLE_QUERIES = {
    "target_locations.csv": f"""
        SELECT DISTINCT loc.city, loc.state, loc.country
        FROM `{DATASET_FULL}.user_job_match_settings`,
        UNNEST(target_locations) AS loc
        WHERE loc.city IS NOT NULL
        ORDER BY loc.state, loc.city
    """,
    "target_roles_ref.csv": f"""
        SELECT DISTINCT alias
        FROM `{DATASET_FULL}.user_job_match_settings`,
        UNNEST(target_roles_ref) AS r
        WHERE r.alias IS NOT NULL
        ORDER BY alias
    """,
    "target_certifications.csv": f"""
        SELECT DISTINCT name
        FROM `{DATASET_FULL}.user_job_match_settings`,
        UNNEST(target_certifications) AS c
        WHERE c.name IS NOT NULL
        ORDER BY name
    """,
    "target_industries.csv": f"""
        SELECT DISTINCT name
        FROM `{DATASET_FULL}.user_job_match_settings`,
        UNNEST(target_industries) AS i
        WHERE i.name IS NOT NULL
        ORDER BY name
    """,
    "target_education_fields.csv": f"""
        SELECT DISTINCT e.name, e.education_level
        FROM `{DATASET_FULL}.user_job_match_settings`,
        UNNEST(target_education_fields) AS e
        WHERE e.name IS NOT NULL
        ORDER BY e.education_level, e.name
    """,
    "job_postings_role_names.csv": f"""
        SELECT DISTINCT role_name
        FROM `{DATASET_FULL}.job_postings`
        WHERE role_name IS NOT NULL
        ORDER BY role_name
    """,
    "xml_categories.csv": f"""
        SELECT DISTINCT category, COUNT(*) as count
        FROM `{DATASET_FULL}.xml_job_feed_raw_jobs`
        WHERE category IS NOT NULL
        GROUP BY category
        ORDER BY count DESC
    """,
    "xml_segment_names.csv": f"""
        SELECT DISTINCT segment_name, COUNT(*) as count
        FROM `{DATASET_FULL}.xml_job_feed_raw_jobs`
        WHERE segment_name IS NOT NULL
        GROUP BY segment_name
        ORDER BY count DESC
    """,
}


def export_simple_queries():
    print("\n=== Exporting simple query CSVs ===")
    for filename, sql in SIMPLE_QUERIES.items():
        print(f"  Running query for {filename}...")
        try:
            df = bq_client.run_query(sql)
            path = os.path.join(OUTPUT_DIR, filename)
            df.to_csv(path, index=False)
            print(f"    Saved {path} ({os.path.getsize(path):,} bytes, {len(df)} rows)")
        except Exception as e:
            print(f"    ERROR for {filename}: {e}")


# ---------- Main ----------

if __name__ == "__main__":
    print(f"Output directory: {OUTPUT_DIR}\n")
    build_field_reference()
    export_simple_queries()

    print("\n=== Summary ===")
    for f in sorted(os.listdir(OUTPUT_DIR)):
        if f.endswith(".csv"):
            full = os.path.join(OUTPUT_DIR, f)
            size = os.path.getsize(full)
            print(f"  {f:40s} {size:>10,} bytes")
    print("\nDone!")
