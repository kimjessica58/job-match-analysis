import os
from dotenv import load_dotenv

load_dotenv()

PROJECT_ID = "expert-octo-production-394601"
DATASET = "prod_batch_expert_octo_db_main"

# Available tables
TABLES = {
    "user_job_match_settings": {
        "full": f"{PROJECT_ID}.{DATASET}.user_job_match_settings",
        "label": "Job Match Settings",
    },
    "user": {
        "full": f"{PROJECT_ID}.{DATASET}.user",
        "label": "User",
    },
    "user_job_match_auto_apply_posting_match": {
        "full": f"{PROJECT_ID}.{DATASET}.user_job_match_auto_apply_posting_match",
        "label": "Posting Match",
    },
    "user_job_match_auto_apply_posting": {
        "full": f"{PROJECT_ID}.{DATASET}.user_job_match_auto_apply_posting",
        "label": "Auto Apply Posting",
    },
    "job_postings": {
        "full": f"{PROJECT_ID}.{DATASET}.job_postings",
        "label": "Job Postings",
    },
    "xml_job_feed_raw_jobs": {
        "full": f"{PROJECT_ID}.{DATASET}.xml_job_feed_raw_jobs",
        "label": "XML Job Feed",
    },
}

# Default table
TABLE = "user_job_match_settings"
FULL_TABLE = TABLES[TABLE]["full"]

# Join relationships
JOINS = {
    ("user_job_match_settings", "user"): ("user_id", "id"),
    ("user_job_match_settings", "user_job_match_auto_apply_posting_match"): ("uuid", "user_job_match_settings_uuid"),
}

# RECORD (nested/repeated) columns
RECORD_COLUMNS = {
    "user_job_match_settings": [],
}

# Custom SQL expressions for specific columns (overrides default RECORD handling)
CUSTOM_COLUMN_EXPR = {
    ("user_job_match_settings", "target_locations"): (
        "(SELECT STRING_AGG(CONCAT(loc.city, ', ', loc.state), ' | ') "
        "FROM UNNEST({alias}.target_locations) AS loc) AS target_locations"
    ),
    ("user_job_match_settings", "target_locations_zip"): (
        "(SELECT STRING_AGG(CONCAT(loc.city, ', ', loc.state, ' ', loc.zipcode), ' | ') "
        "FROM UNNEST({alias}.target_locations) AS loc) AS target_locations_zip"
    ),
    ("user_job_match_settings", "target_roles_ref"): (
        "(SELECT STRING_AGG(r.alias, ' | ') "
        "FROM UNNEST({alias}.target_roles_ref) AS r) AS target_roles_ref"
    ),
    ("user_job_match_settings", "target_industries"): (
        "(SELECT STRING_AGG(i.name, ' | ') "
        "FROM UNNEST({alias}.target_industries) AS i) AS target_industries"
    ),
    ("user_job_match_settings", "target_certifications"): (
        "(SELECT STRING_AGG(c.name, ' | ') "
        "FROM UNNEST({alias}.target_certifications) AS c) AS target_certifications"
    ),
    ("user_job_match_settings", "target_education_fields"): (
        "(SELECT STRING_AGG(CONCAT(e.name, ' (', e.education_level, ')'), ' | ') "
        "FROM UNNEST({alias}.target_education_fields) AS e) AS target_education_fields"
    ),
    ("user_job_match_settings", "target_neighborhoods"): (
        "(SELECT STRING_AGG(CONCAT(n.name, ', ', n.city), ' | ') "
        "FROM UNNEST({alias}.target_neighborhoods) AS n) AS target_neighborhoods"
    ),
    ("user_job_match_settings", "target_transit_lines"): (
        "(SELECT STRING_AGG(t.name, ' | ') "
        "FROM UNNEST({alias}.target_transit_lines) AS t) AS target_transit_lines"
    ),
    ("user_job_match_settings", "target_role_class"): (
        "(SELECT STRING_AGG(CONCAT(rc.major_group, ' > ', rc.broad_group), ' | ') "
        "FROM UNNEST({alias}.target_role_class) AS rc) AS target_role_class"
    ),
}

# Path to service account key
CREDENTIALS_PATH = os.getenv(
    "GOOGLE_APPLICATION_CREDENTIALS",
    "credentials/service-account.json"
)

# Path to data model reference doc (used by Query Lab)
CLAUDE_MD_PATH = os.path.join(os.path.dirname(__file__), "reference", "claude.md")

# Anthropic API key for Query Lab
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
if not ANTHROPIC_API_KEY:
    try:
        import streamlit as st
        ANTHROPIC_API_KEY = st.secrets.get("ANTHROPIC_API_KEY", "")
    except Exception:
        pass

# Dashboard defaults
CACHE_TTL = 3600  # 1 hour
DEFAULT_ROW_LIMIT = 1000
