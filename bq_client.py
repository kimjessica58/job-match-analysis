import os
import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account
import config

APPROVED_MATCH_STATUSES = (
    "('USER_APPROVED', 'CONTRACTOR_PENDING', 'APPLIED', 'APP_FAILED', 'ACCOUNT_EXISTS')"
)
DECIDED_MATCH_STATUSES = (
    "('USER_APPROVED', 'CONTRACTOR_PENDING', 'APPLIED', 'APP_FAILED', "
    "'ACCOUNT_EXISTS', 'USER_REJECTED', 'JOB_EXPIRED')"
)
FAILURE_MATCH_STATUSES = "('APP_FAILED', 'ACCOUNT_EXISTS', 'JOB_EXPIRED')"


def _normalize_date(value):
    """Normalize date or datetime-like values to ISO date strings."""
    if value is None:
        return None
    return pd.Timestamp(value).date().isoformat()


def _date_clause(field, start_date=None, end_date=None):
    """Build a DATE(field) filter clause."""
    start = _normalize_date(start_date)
    end = _normalize_date(end_date)
    clauses = []
    if start:
        clauses.append(f"DATE({field}) >= DATE '{start}'")
    if end:
        clauses.append(f"DATE({field}) <= DATE '{end}'")
    return " AND ".join(clauses)


def _where(*clauses):
    """Build a WHERE statement from non-empty clauses."""
    parts = [clause for clause in clauses if clause]
    return f"WHERE {' AND '.join(parts)}" if parts else ""


def _active_settings_predicate(field="status"):
    """Treat every non-paused settings record as in-scope for dashboard analysis."""
    return f"COALESCE({field}, '') != 'PAUSED'"


def _resume_ready_predicate(field="default_resume_id"):
    """Require a user to have a default resume to be considered match-ready."""
    return f"{field} IS NOT NULL"


def _active_match_user_predicate(status_field="status", resume_field="default_resume_id"):
    """Current dashboard definition of an active match user."""
    return f"{_active_settings_predicate(status_field)} AND {_resume_ready_predicate(resume_field)}"


def _latest_settings_snapshot_query():
    """Return the latest settings row per user joined to the user account."""
    settings_full = get_full_table("user_job_match_settings")
    user_full = get_full_table("user")
    return f"""
    SELECT
        s.*,
        u.default_resume_id
    FROM (
        SELECT *
        FROM `{settings_full}`
        WHERE user_id IS NOT NULL
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY user_id
            ORDER BY COALESCE(updated_at, created_at) DESC, created_at DESC, uuid DESC
        ) = 1
    ) s
    JOIN `{user_full}` u
      ON s.user_id = u.id
    """


def _latest_settings_snapshot_cte(name="latest_settings_snapshot"):
    """Return the latest settings snapshot joined to user state."""
    return f"""
    {name} AS (
        {_latest_settings_snapshot_query()}
    )
    """


def _latest_active_settings_cte(name="latest_active_settings", snapshot_name="latest_settings_snapshot"):
    """Return the latest active match-user settings row per user."""
    return f"""
    {name} AS (
        SELECT *
        FROM {snapshot_name}
        WHERE {_active_match_user_predicate("status", "default_resume_id")}
    )
    """


def _active_match_user_ids_subquery():
    """Return current active match-user ids for filtering match tables."""
    return f"""
    SELECT user_id
    FROM (
        {_latest_settings_snapshot_query()}
    )
    WHERE {_active_match_user_predicate("status", "default_resume_id")}
    """


def _match_source_predicate(match_source="all", auto_alias="ap", posting_alias="jp"):
    """Build a predicate for XML/native match-source filtering."""
    xml_predicate = f"({auto_alias}.xml_raw_job_uuid IS NOT NULL OR {posting_alias}.xml_job_uuid IS NOT NULL)"
    if match_source == "xml":
        return xml_predicate
    if match_source == "native":
        return f"NOT {xml_predicate}"
    return ""


def _filtered_matches_cte(name="filtered_matches", start_date=None, end_date=None, match_source="all"):
    """Return a reusable CTE for filtered posting matches."""
    match_full = get_full_table("user_job_match_auto_apply_posting_match")
    settings_full = get_full_table("user_job_match_settings")
    auto_full = get_full_table("user_job_match_auto_apply_posting")
    posting_full = get_full_table("job_postings")
    where_clause = _where(
        _date_clause("m.created_at", start_date, end_date),
        _match_source_predicate(match_source, auto_alias="ap", posting_alias="jp"),
    )
    return f"""
    {name} AS (
        SELECT m.*
        FROM `{match_full}` m
        JOIN `{settings_full}` s
          ON m.user_job_match_settings_uuid = s.uuid
        JOIN (
            {_active_match_user_ids_subquery()}
        ) active_match_users
          ON s.user_id = active_match_users.user_id
        LEFT JOIN `{auto_full}` ap
          ON m.auto_apply_posting_uuid = ap.uuid
        LEFT JOIN `{posting_full}` jp
          ON ap.posting_uuid = jp.uuid
        {where_clause}
    )
    """


def _filtered_xml_matches_cte(name="xml_matches", start_date=None, end_date=None):
    """Return a reusable CTE with resolved XML job UUIDs."""
    match_full = get_full_table("user_job_match_auto_apply_posting_match")
    settings_full = get_full_table("user_job_match_settings")
    auto_full = get_full_table("user_job_match_auto_apply_posting")
    posting_full = get_full_table("job_postings")
    where_clause = _where(
        _date_clause("m.created_at", start_date, end_date),
        _match_source_predicate("xml", auto_alias="ap", posting_alias="jp"),
    )
    return f"""
    {name} AS (
        SELECT
            m.*,
            COALESCE(ap.xml_raw_job_uuid, jp.xml_job_uuid) AS xml_job_uuid
        FROM `{match_full}` m
        JOIN `{settings_full}` s
          ON m.user_job_match_settings_uuid = s.uuid
        JOIN (
            {_active_match_user_ids_subquery()}
        ) active_match_users
          ON s.user_id = active_match_users.user_id
        LEFT JOIN `{auto_full}` ap
          ON m.auto_apply_posting_uuid = ap.uuid
        LEFT JOIN `{posting_full}` jp
          ON ap.posting_uuid = jp.uuid
        {where_clause}
    )
    """


def _resolve_match_window(start_date=None, end_date=None, days=None):
    """Apply a default trailing window when no explicit match dates are provided."""
    if start_date is None and end_date is None and days is not None:
        return pd.Timestamp.utcnow().normalize() - pd.Timedelta(days=days - 1), None
    return start_date, end_date


def get_client():
    """Create an authenticated BigQuery client.

    Uses local service account JSON file if available, otherwise falls back
    to Streamlit Community Cloud secrets (st.secrets["gcp_service_account"]).
    """
    creds_path = config.CREDENTIALS_PATH
    if os.path.exists(creds_path):
        credentials = service_account.Credentials.from_service_account_file(
            creds_path,
            scopes=["https://www.googleapis.com/auth/bigquery"],
        )
    else:
        try:
            import streamlit as st
            creds_info = dict(st.secrets["gcp_service_account"])
            credentials = service_account.Credentials.from_service_account_info(
                creds_info,
                scopes=["https://www.googleapis.com/auth/bigquery"],
            )
        except Exception:
            raise FileNotFoundError(
                f"Service account key not found at '{creds_path}' and no "
                "Streamlit secrets configured. Either place your key at "
                "credentials/service-account.json or add gcp_service_account "
                "to Streamlit secrets."
            )
    return bigquery.Client(project=config.PROJECT_ID, credentials=credentials)


def run_query(sql, params=None):
    """Execute a SQL query and return results as a pandas DataFrame."""
    client = get_client()
    job_config = bigquery.QueryJobConfig()
    if params:
        job_config.query_parameters = params
    return client.query(sql, job_config=job_config).to_dataframe()


def get_table_schema(table_name=None):
    """Fetch column names and data types for a table."""
    table_name = table_name or config.TABLE
    sql = f"""
    SELECT column_name, data_type, is_nullable
    FROM `{config.PROJECT_ID}.{config.DATASET}.INFORMATION_SCHEMA.COLUMNS`
    WHERE table_name = @table_name
    ORDER BY ordinal_position
    """
    params = [
        bigquery.ScalarQueryParameter("table_name", "STRING", table_name),
    ]
    return run_query(sql, params)


def get_full_table(table_name=None):
    """Get the fully qualified table name."""
    table_name = table_name or config.TABLE
    return config.TABLES[table_name]["full"]


def get_row_count(table_name=None, where_clause=""):
    """Get the total row count, optionally filtered."""
    full_table = get_full_table(table_name)
    where = f"WHERE {where_clause}" if where_clause else ""
    sql = f"SELECT COUNT(*) as total_rows FROM `{full_table}` {where}"
    df = run_query(sql)
    return int(df["total_rows"].iloc[0])


def query_data(table_name=None, columns=None, where_clause="", order_by=None, limit=None):
    """Query a table with optional filters."""
    full_table = get_full_table(table_name)
    col_str = ", ".join(columns) if columns else "*"
    where = f"WHERE {where_clause}" if where_clause else ""
    order = f"ORDER BY {order_by} DESC" if order_by else ""
    row_limit = limit or config.DEFAULT_ROW_LIMIT
    sql = f"""
    SELECT {col_str}
    FROM `{full_table}`
    {where}
    {order}
    LIMIT {row_limit}
    """
    return run_query(sql)


def query_three_way_join(settings_columns=None, user_columns=None, posting_columns=None,
                         where_clause="", order_by=None, limit=None):
    """Query settings + user + posting match joined together."""
    settings_full = get_full_table("user_job_match_settings")
    user_full = get_full_table("user")
    posting_full = get_full_table("user_job_match_auto_apply_posting_match")

    settings_records = set(config.RECORD_COLUMNS.get("user_job_match_settings", []))
    user_records = set(config.RECORD_COLUMNS.get("user", []))
    posting_records = set(config.RECORD_COLUMNS.get("user_job_match_auto_apply_posting_match", []))

    TABLE_FOR_ALIAS = {"s": "user_job_match_settings", "u": "user", "p": "user_job_match_auto_apply_posting_match"}

    def _col_expr(alias, col, record_set):
        table_name = TABLE_FOR_ALIAS.get(alias, "")
        custom_key = (table_name, col)
        if custom_key in config.CUSTOM_COLUMN_EXPR:
            return config.CUSTOM_COLUMN_EXPR[custom_key].format(alias=alias)
        if col in record_set:
            return f"TO_JSON_STRING({alias}.{col}) AS {col}"
        return f"{alias}.{col}"

    select_parts = []
    if settings_columns:
        select_parts.extend([_col_expr("s", c, settings_records) for c in settings_columns])
    else:
        select_parts.append("s.*")
    if user_columns:
        select_parts.extend([_col_expr("u", c, user_records) for c in user_columns])
    else:
        select_parts.append("u.*")
    if posting_columns:
        select_parts.extend([_col_expr("p", c, posting_records) for c in posting_columns])
    else:
        select_parts.append("p.*")
    col_str = ", ".join(select_parts)

    where = f"WHERE {where_clause}" if where_clause else ""
    order = f"ORDER BY {order_by} DESC" if order_by else ""
    row_limit = limit or config.DEFAULT_ROW_LIMIT

    sql = f"""
    SELECT {col_str}
    FROM `{settings_full}` s
    LEFT JOIN `{user_full}` u ON s.user_id = u.id
    LEFT JOIN `{posting_full}` p ON s.uuid = p.user_job_match_settings_uuid
    {where}
    {order}
    LIMIT {row_limit}
    """
    return run_query(sql)


# ── Overview KPIs ─────────────────────────────────────────────────────────────

def get_overview_kpis(start_date=None, end_date=None, match_source="all"):
    """Get key metrics for the overview dashboard."""
    sql = f"""
    WITH {_latest_settings_snapshot_cte()},
    {_latest_active_settings_cte()},
    {_filtered_matches_cte(start_date=start_date, end_date=end_date, match_source=match_source)}
    SELECT
        (SELECT COUNT(*) FROM latest_active_settings) AS total_settings,
        (SELECT COUNT(*) FROM latest_active_settings WHERE status = 'ACTIVE') AS active_users,
        (SELECT COUNT(*) FROM latest_settings_snapshot WHERE {_resume_ready_predicate("default_resume_id")} AND COALESCE(status, '') = 'PAUSED') AS paused_users,
        (
            SELECT SAFE_DIVIDE(
                COUNTIF(COALESCE(status, '') = 'PAUSED'),
                COUNT(*)
            )
            FROM latest_settings_snapshot
            WHERE {_resume_ready_predicate("default_resume_id")}
        ) AS paused_rate,
        (SELECT COUNT(*) FROM filtered_matches) AS total_matches,
        (SELECT COUNT(*) FROM filtered_matches WHERE DATE(created_at) = CURRENT_DATE()) AS matches_today,
        (SELECT COUNT(*) FROM filtered_matches WHERE created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)) AS matches_this_week,
        (SELECT COUNT(*) FROM filtered_matches WHERE created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)) AS matches_this_month,
        (SELECT COUNT(*) FROM filtered_matches WHERE status = 'USER_APPROVED') AS approved_count,
        (SELECT COUNT(*) FROM filtered_matches WHERE status = 'APPLIED') AS applied_count,
        (SELECT COUNT(*) FROM filtered_matches WHERE status = 'USER_REJECTED') AS rejected_count,
        (SELECT COUNT(*) FROM filtered_matches WHERE status IN ('USER_APPROVED', 'CONTRACTOR_PENDING', 'APPLIED', 'APP_FAILED', 'ACCOUNT_EXISTS')) AS past_pending_count
    """
    return run_query(sql)


def get_match_performance_summary(start_date=None, end_date=None, match_source="all"):
    """Get overall counts and rates for the match lifecycle."""
    sql = f"""
    WITH {_filtered_matches_cte(start_date=start_date, end_date=end_date, match_source=match_source)}
    SELECT
        COUNT(*) AS total_matches,
        COUNTIF(status = 'USER_PENDING') AS pending_matches,
        COUNTIF(status IN {DECIDED_MATCH_STATUSES}) AS decided_matches,
        COUNTIF(status IN {APPROVED_MATCH_STATUSES}) AS approved_matches,
        COUNTIF(status = 'USER_REJECTED') AS rejected_matches,
        COUNTIF(status = 'APPLIED') AS applied_matches,
        COUNTIF(status = 'APP_FAILED') AS failed_matches,
        COUNTIF(status = 'ACCOUNT_EXISTS') AS account_exists_matches,
        COUNTIF(status = 'JOB_EXPIRED') AS expired_matches,
        SAFE_DIVIDE(COUNTIF(status IN {DECIDED_MATCH_STATUSES}), COUNT(*)) AS decision_rate,
        SAFE_DIVIDE(COUNTIF(status IN {APPROVED_MATCH_STATUSES}), COUNTIF(status IN {DECIDED_MATCH_STATUSES})) AS approval_rate,
        SAFE_DIVIDE(COUNTIF(status = 'USER_REJECTED'), COUNTIF(status IN {DECIDED_MATCH_STATUSES})) AS rejection_rate,
        SAFE_DIVIDE(COUNTIF(status = 'APPLIED'), COUNTIF(status IN {APPROVED_MATCH_STATUSES})) AS application_rate
    FROM filtered_matches
    """
    return run_query(sql)


def get_weekly_match_cohort_performance(weeks=26, maturity_days=28, start_date=None, end_date=None, match_source="all"):
    """Get mature weekly match cohorts with lifecycle rates."""
    sql = f"""
    WITH {_filtered_matches_cte(start_date=start_date, end_date=end_date, match_source=match_source)},
    weekly AS (
        SELECT
            DATE_TRUNC(DATE(created_at), WEEK(MONDAY)) AS cohort_week,
            COUNT(*) AS total_matches,
            COUNTIF(status = 'USER_PENDING') AS pending_matches,
            COUNTIF(status IN {DECIDED_MATCH_STATUSES}) AS decided_matches,
            COUNTIF(status IN {APPROVED_MATCH_STATUSES}) AS approved_matches,
            COUNTIF(status = 'USER_REJECTED') AS rejected_matches,
            COUNTIF(status = 'APPLIED') AS applied_matches,
            COUNTIF(status = 'APP_FAILED') AS failed_matches,
            COUNTIF(status = 'ACCOUNT_EXISTS') AS account_exists_matches,
            COUNTIF(status = 'JOB_EXPIRED') AS expired_matches,
            SAFE_DIVIDE(COUNTIF(status IN {DECIDED_MATCH_STATUSES}), COUNT(*)) AS decision_rate,
            SAFE_DIVIDE(COUNTIF(status IN {APPROVED_MATCH_STATUSES}), COUNTIF(status IN {DECIDED_MATCH_STATUSES})) AS approval_rate,
            SAFE_DIVIDE(COUNTIF(status = 'USER_REJECTED'), COUNTIF(status IN {DECIDED_MATCH_STATUSES})) AS rejection_rate,
            SAFE_DIVIDE(COUNTIF(status = 'APPLIED'), COUNTIF(status IN {APPROVED_MATCH_STATUSES})) AS application_rate
        FROM filtered_matches
        WHERE created_at IS NOT NULL
          AND DATE(created_at) < DATE_SUB(CURRENT_DATE(), INTERVAL {maturity_days} DAY)
        GROUP BY cohort_week
    )
    SELECT *
    FROM weekly
    QUALIFY ROW_NUMBER() OVER (ORDER BY cohort_week DESC) <= {weeks}
    ORDER BY cohort_week
    """
    return run_query(sql)


def get_signup_cohort_performance(months=12, window_weeks=12, start_date=None, end_date=None, match_source="all"):
    """Compare monthly signup cohorts over the same post-signup window."""
    settings_full = get_full_table("user_job_match_settings")
    settings_date = _date_clause("created_at", start_date, end_date)
    sql = f"""
    WITH {_latest_settings_snapshot_cte()},
    {_latest_active_settings_cte()},
    {_filtered_matches_cte(start_date=start_date, end_date=end_date, match_source=match_source)},
    eligible_settings AS (
        SELECT
            uuid,
            user_id,
            DATE(created_at) AS signup_date,
            DATE_TRUNC(DATE(created_at), MONTH) AS signup_month
        FROM latest_active_settings
        WHERE created_at IS NOT NULL
          AND DATE(created_at) <= DATE_SUB(CURRENT_DATE(), INTERVAL {window_weeks} WEEK)
          {"AND " + settings_date if settings_date else ""}
    ),
    latest_months AS (
        SELECT signup_month
        FROM eligible_settings
        GROUP BY signup_month
        QUALIFY ROW_NUMBER() OVER (ORDER BY signup_month DESC) <= {months}
    ),
    cohort_sizes AS (
        SELECT
            e.signup_month,
            COUNT(DISTINCT e.user_id) AS cohort_users
        FROM eligible_settings e
        JOIN latest_months lm USING (signup_month)
        GROUP BY e.signup_month
    ),
    match_users AS (
        SELECT
            s.user_id,
            m.created_at,
            m.status
        FROM filtered_matches m
        JOIN `{settings_full}` s
          ON m.user_job_match_settings_uuid = s.uuid
        WHERE s.user_id IS NOT NULL
    ),
    cohort_matches AS (
        SELECT
            e.signup_month,
            m.status
        FROM eligible_settings e
        JOIN latest_months lm USING (signup_month)
        LEFT JOIN match_users m
          ON e.user_id = m.user_id
         AND m.created_at IS NOT NULL
         AND DATE_DIFF(DATE(m.created_at), e.signup_date, WEEK(MONDAY)) BETWEEN 0 AND {window_weeks - 1}
    )
    SELECT
        cm.signup_month,
        cs.cohort_users,
        COUNTIF(cm.status IS NOT NULL) AS total_matches,
        SAFE_DIVIDE(COUNTIF(cm.status IS NOT NULL), cs.cohort_users) AS matches_per_user,
        COUNTIF(cm.status IN {DECIDED_MATCH_STATUSES}) AS decided_matches,
        COUNTIF(cm.status IN {APPROVED_MATCH_STATUSES}) AS approved_matches,
        COUNTIF(cm.status = 'USER_REJECTED') AS rejected_matches,
        COUNTIF(cm.status = 'APPLIED') AS applied_matches,
        SAFE_DIVIDE(COUNTIF(cm.status IN {DECIDED_MATCH_STATUSES}), COUNTIF(cm.status IS NOT NULL)) AS decision_rate,
        SAFE_DIVIDE(COUNTIF(cm.status IN {APPROVED_MATCH_STATUSES}), COUNTIF(cm.status IN {DECIDED_MATCH_STATUSES})) AS approval_rate,
        SAFE_DIVIDE(COUNTIF(cm.status = 'USER_REJECTED'), COUNTIF(cm.status IN {DECIDED_MATCH_STATUSES})) AS rejection_rate,
        SAFE_DIVIDE(COUNTIF(cm.status = 'APPLIED'), COUNTIF(cm.status IN {APPROVED_MATCH_STATUSES})) AS application_rate
    FROM cohort_matches cm
    JOIN cohort_sizes cs USING (signup_month)
    GROUP BY cm.signup_month, cs.cohort_users
    ORDER BY cm.signup_month
    """
    return run_query(sql)


def get_signup_cohort_evolution(quarters=6, window_weeks=12, start_date=None, end_date=None, match_source="all"):
    """Track how quarterly signup cohorts perform week-by-week after signup."""
    settings_full = get_full_table("user_job_match_settings")
    settings_date = _date_clause("created_at", start_date, end_date)
    sql = f"""
    WITH {_latest_settings_snapshot_cte()},
    {_latest_active_settings_cte()},
    {_filtered_matches_cte(start_date=start_date, end_date=end_date, match_source=match_source)},
    eligible_settings AS (
        SELECT
            uuid,
            user_id,
            DATE(created_at) AS signup_date,
            DATE_TRUNC(DATE(created_at), QUARTER) AS signup_cohort
        FROM latest_active_settings
        WHERE created_at IS NOT NULL
          AND DATE(created_at) <= DATE_SUB(CURRENT_DATE(), INTERVAL {window_weeks} WEEK)
          {"AND " + settings_date if settings_date else ""}
    ),
    latest_cohorts AS (
        SELECT signup_cohort
        FROM eligible_settings
        GROUP BY signup_cohort
        QUALIFY ROW_NUMBER() OVER (ORDER BY signup_cohort DESC) <= {quarters}
    ),
    cohort_sizes AS (
        SELECT
            e.signup_cohort,
            COUNT(DISTINCT e.user_id) AS cohort_users
        FROM eligible_settings e
        JOIN latest_cohorts lc USING (signup_cohort)
        GROUP BY e.signup_cohort
    ),
    weeks AS (
        SELECT week
        FROM UNNEST(GENERATE_ARRAY(0, {window_weeks - 1})) AS week
    ),
    match_users AS (
        SELECT
            s.user_id,
            m.created_at,
            m.status
        FROM filtered_matches m
        JOIN `{settings_full}` s
          ON m.user_job_match_settings_uuid = s.uuid
        WHERE s.user_id IS NOT NULL
    ),
    match_events AS (
        SELECT
            e.signup_cohort,
            DATE_DIFF(DATE(m.created_at), e.signup_date, WEEK(MONDAY)) AS weeks_since_signup,
            m.status
        FROM eligible_settings e
        JOIN latest_cohorts lc USING (signup_cohort)
        JOIN match_users m
          ON e.user_id = m.user_id
        WHERE m.created_at IS NOT NULL
          AND DATE_DIFF(DATE(m.created_at), e.signup_date, WEEK(MONDAY)) BETWEEN 0 AND {window_weeks - 1}
    ),
    weekly AS (
        SELECT
            signup_cohort,
            weeks_since_signup,
            COUNT(*) AS matches,
            COUNTIF(status IN {DECIDED_MATCH_STATUSES}) AS decided_matches,
            COUNTIF(status IN {APPROVED_MATCH_STATUSES}) AS approved_matches,
            COUNTIF(status = 'USER_REJECTED') AS rejected_matches,
            COUNTIF(status = 'APPLIED') AS applied_matches
        FROM match_events
        GROUP BY signup_cohort, weeks_since_signup
    )
    SELECT
        lc.signup_cohort,
        w.week AS weeks_since_signup,
        cs.cohort_users,
        COALESCE(weekly.matches, 0) AS matches,
        SAFE_DIVIDE(COALESCE(weekly.matches, 0), cs.cohort_users) AS matches_per_user,
        SAFE_DIVIDE(weekly.approved_matches, weekly.decided_matches) AS approval_rate,
        SAFE_DIVIDE(weekly.rejected_matches, weekly.decided_matches) AS rejection_rate,
        SAFE_DIVIDE(weekly.applied_matches, weekly.approved_matches) AS application_rate
    FROM latest_cohorts lc
    JOIN cohort_sizes cs USING (signup_cohort)
    CROSS JOIN weeks w
    LEFT JOIN weekly
      ON weekly.signup_cohort = lc.signup_cohort
     AND weekly.weeks_since_signup = w.week
    ORDER BY lc.signup_cohort, w.week
    """
    return run_query(sql)


def get_top_xml_jobs(limit=25, start_date=None, end_date=None):
    """Get top XML jobs by filtered match volume and conversion."""
    xml_full = get_full_table("xml_job_feed_raw_jobs")
    sql = f"""
    WITH {_filtered_xml_matches_cte(start_date=start_date, end_date=end_date)},
    job_rollup AS (
        SELECT
            m.xml_job_uuid,
            COALESCE(NULLIF(x.role_name, ''), 'Unknown') AS role_name,
            COALESCE(NULLIF(x.company_name, ''), 'Unknown') AS company_name,
            COALESCE(
                NULLIF(CONCAT(COALESCE(x.city, ''), ', ', COALESCE(x.state, '')), ', '),
                NULLIF(x.location, ''),
                'Unknown'
            ) AS location,
            COALESCE(NULLIF(x.segment_name, ''), 'Unknown') AS segment_name,
            COALESCE(NULLIF(x.category, ''), 'Unknown') AS category,
            COUNT(*) AS total_matches,
            COUNTIF(m.status IN {DECIDED_MATCH_STATUSES}) AS decided_matches,
            COUNTIF(m.status IN {APPROVED_MATCH_STATUSES}) AS approved_matches,
            COUNTIF(m.status = 'APPLIED') AS applied_matches,
            COUNTIF(m.status = 'APP_FAILED') AS app_failed_matches,
            COUNTIF(m.status = 'ACCOUNT_EXISTS') AS account_exists_matches,
            COUNTIF(m.status = 'JOB_EXPIRED') AS expired_matches,
            COUNTIF(m.status IN {FAILURE_MATCH_STATUSES}) AS failure_matches,
            SUM(CASE WHEN m.status = 'APPLIED' THEN COALESCE(m.cpa, 0) ELSE 0 END) AS realized_cpa
        FROM xml_matches m
        LEFT JOIN `{xml_full}` x
          ON m.xml_job_uuid = x.uuid
        GROUP BY 1, 2, 3, 4, 5, 6
    )
    SELECT
        *,
        SAFE_DIVIDE(approved_matches, decided_matches) AS approval_rate,
        SAFE_DIVIDE(applied_matches, approved_matches) AS application_rate,
        SAFE_DIVIDE(failure_matches, approved_matches) AS failure_rate_after_approval,
        SAFE_DIVIDE(realized_cpa, NULLIF(applied_matches, 0)) AS avg_cpa_per_application
    FROM job_rollup
    ORDER BY total_matches DESC, applied_matches DESC, realized_cpa DESC
    LIMIT {limit}
    """
    return run_query(sql)


def get_top_match_users(limit=25, start_date=None, end_date=None, match_source="all"):
    """Get users with the most filtered matches and downstream outcomes."""
    settings_full = get_full_table("user_job_match_settings")
    user_full = get_full_table("user")
    sql = f"""
    WITH {_filtered_matches_cte(start_date=start_date, end_date=end_date, match_source=match_source)}
    SELECT
        s.uuid AS settings_uuid,
        s.user_id,
        COALESCE(
            NULLIF(u.name, ''),
            NULLIF(TRIM(CONCAT(COALESCE(u.first_name, ''), ' ', COALESCE(u.last_name, ''))), ''),
            CONCAT('User ', CAST(s.user_id AS STRING))
        ) AS user_name,
        COUNT(*) AS total_matches,
        COUNTIF(m.status IN {DECIDED_MATCH_STATUSES}) AS decided_matches,
        COUNTIF(m.status IN {APPROVED_MATCH_STATUSES}) AS approved_matches,
        COUNTIF(m.status = 'APPLIED') AS applied_matches,
        COUNTIF(m.status = 'APP_FAILED') AS app_failed_matches,
        COUNTIF(m.status = 'ACCOUNT_EXISTS') AS account_exists_matches,
        COUNTIF(m.status = 'JOB_EXPIRED') AS expired_matches,
        COUNTIF(m.status IN {FAILURE_MATCH_STATUSES}) AS failure_matches,
        SUM(CASE WHEN m.status = 'APPLIED' THEN COALESCE(m.cpa, 0) ELSE 0 END) AS realized_cpa,
        SAFE_DIVIDE(COUNTIF(m.status IN {APPROVED_MATCH_STATUSES}), COUNTIF(m.status IN {DECIDED_MATCH_STATUSES})) AS approval_rate,
        SAFE_DIVIDE(COUNTIF(m.status = 'APPLIED'), COUNTIF(m.status IN {APPROVED_MATCH_STATUSES})) AS application_rate,
        SAFE_DIVIDE(COUNTIF(m.status IN {FAILURE_MATCH_STATUSES}), COUNTIF(m.status IN {APPROVED_MATCH_STATUSES})) AS failure_rate_after_approval
    FROM filtered_matches m
    LEFT JOIN `{settings_full}` s
      ON m.user_job_match_settings_uuid = s.uuid
    LEFT JOIN `{user_full}` u
      ON s.user_id = u.id
    GROUP BY 1, 2, 3
    ORDER BY total_matches DESC, applied_matches DESC, realized_cpa DESC
    LIMIT {limit}
    """
    return run_query(sql)


def get_match_failure_breakdown(start_date=None, end_date=None, match_source="all"):
    """Break down post-approval failures for the filtered match set."""
    sql = f"""
    WITH {_filtered_matches_cte(start_date=start_date, end_date=end_date, match_source=match_source)},
    totals AS (
        SELECT
            COUNTIF(status IN {APPROVED_MATCH_STATUSES}) AS approved_matches,
            COUNTIF(status IN {FAILURE_MATCH_STATUSES}) AS total_failures
        FROM filtered_matches
    ),
    breakdown AS (
        SELECT
            status,
            COUNT(*) AS failure_count
        FROM filtered_matches
        WHERE status IN {FAILURE_MATCH_STATUSES}
        GROUP BY status
    )
    SELECT
        b.status,
        b.failure_count,
        SAFE_DIVIDE(b.failure_count, t.total_failures) AS share_of_failures,
        SAFE_DIVIDE(b.failure_count, t.approved_matches) AS failure_rate_after_approval
    FROM breakdown b
    CROSS JOIN totals t
    ORDER BY b.failure_count DESC
    """
    return run_query(sql)


# ── Status / Distribution Queries ─────────────────────────────────────────────

def get_status_distribution(table_name, column, start_date=None, end_date=None, date_field="created_at"):
    """Get value counts for a column."""
    if table_name == "user_job_match_settings":
        date_where = _date_clause(date_field, start_date, end_date)
        sql = f"""
        WITH {_latest_settings_snapshot_cte()},
        {_latest_active_settings_cte()}
        SELECT {column} AS value, COUNT(*) AS count
        FROM latest_active_settings
        {_where(f"{column} IS NOT NULL", date_where)}
        GROUP BY {column}
        ORDER BY count DESC
        """
        return run_query(sql)

    full_table = get_full_table(table_name)
    date_where = _date_clause(date_field, start_date, end_date)
    where_clauses = [f"{column} IS NOT NULL", date_where]
    where_clause = _where(*where_clauses)
    sql = f"""
    SELECT {column} AS value, COUNT(*) AS count
    FROM `{full_table}`
    {where_clause}
    GROUP BY {column}
    ORDER BY count DESC
    """
    return run_query(sql)


# ── Match Funnel ──────────────────────────────────────────────────────────────

def get_match_funnel(start_date=None, end_date=None, match_source="all"):
    """Get match counts by status."""
    sql_start, sql_end = _resolve_match_window(start_date, end_date)
    sql = f"""
    WITH {_filtered_matches_cte(start_date=sql_start, end_date=sql_end, match_source=match_source)}
    SELECT status, COUNT(*) AS count
    FROM filtered_matches
    WHERE status IS NOT NULL
    GROUP BY status
    ORDER BY count DESC
    """
    return run_query(sql)


def get_match_funnel_by_version(start_date=None, end_date=None, match_source="all"):
    """Get match funnel broken down by match_generation_version."""
    sql_start, sql_end = _resolve_match_window(start_date, end_date)
    sql = f"""
    WITH {_filtered_matches_cte(start_date=sql_start, end_date=sql_end, match_source=match_source)}
    SELECT
        IFNULL(match_generation_version, 'unknown') AS version,
        status,
        COUNT(*) AS count
    FROM filtered_matches
    WHERE status IS NOT NULL
    GROUP BY version, status
    ORDER BY version, count DESC
    """
    return run_query(sql)


def get_match_status_over_time(days=90, start_date=None, end_date=None, match_source="all"):
    """Get daily match counts by status."""
    sql_start, sql_end = _resolve_match_window(start_date, end_date, days=days)
    sql = f"""
    WITH {_filtered_matches_cte(start_date=sql_start, end_date=sql_end, match_source=match_source)}
    SELECT
        DATE(created_at) AS date,
        status,
        COUNT(*) AS count
    FROM filtered_matches
    WHERE status IS NOT NULL
    GROUP BY date, status
    ORDER BY date
    """
    return run_query(sql)


# ── User Cohorts ──────────────────────────────────────────────────────────────

def get_signup_cohorts(start_date=None, end_date=None):
    """Get user signups by month."""
    sql = f"""
    WITH {_latest_settings_snapshot_cte()},
    {_latest_active_settings_cte()}
    SELECT
        DATE_TRUNC(created_at, MONTH) AS month,
        status,
        COUNT(*) AS count
    FROM latest_active_settings
    {_where("created_at IS NOT NULL", _date_clause("created_at", start_date, end_date))}
    GROUP BY month, status
    ORDER BY month
    """
    return run_query(sql)


def get_engagement_buckets(start_date=None, end_date=None):
    """Categorize users by last activity recency."""
    sql = f"""
    WITH {_latest_settings_snapshot_cte()},
    {_latest_active_settings_cte()}
    SELECT
        CASE
            WHEN last_job_match_activity_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY) THEN 'Last 24h'
            WHEN last_job_match_activity_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY) THEN 'Last 7 days'
            WHEN last_job_match_activity_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY) THEN 'Last 30 days'
            WHEN last_job_match_activity_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY) THEN '30-90 days'
            WHEN last_job_match_activity_at IS NOT NULL THEN '90+ days'
            ELSE 'Never'
        END AS bucket,
        COUNT(*) AS count
    FROM latest_active_settings
    {_where(_date_clause("created_at", start_date, end_date))}
    GROUP BY bucket
    ORDER BY
        CASE bucket
            WHEN 'Last 24h' THEN 1
            WHEN 'Last 7 days' THEN 2
            WHEN 'Last 30 days' THEN 3
            WHEN '30-90 days' THEN 4
            WHEN '90+ days' THEN 5
            WHEN 'Never' THEN 6
        END
    """
    return run_query(sql)


# ── Location Analysis ─────────────────────────────────────────────────────────

def get_state_distribution(start_date=None, end_date=None):
    """Get count of target locations by state."""
    sql = f"""
    WITH {_latest_settings_snapshot_cte()},
    {_latest_active_settings_cte()}
    SELECT loc.state AS state, COUNT(*) AS count
    FROM latest_active_settings s, UNNEST(s.target_locations) AS loc
    WHERE loc.state IS NOT NULL
      AND loc.state != ''
    GROUP BY loc.state
    ORDER BY count DESC
    """
    return run_query(sql)


def get_city_distribution(limit=50, start_date=None, end_date=None):
    """Get top cities by user preference count."""
    sql = f"""
    WITH {_latest_settings_snapshot_cte()},
    {_latest_active_settings_cte()}
    SELECT
        CONCAT(loc.city, ', ', loc.state) AS location,
        loc.city,
        loc.state,
        COUNT(*) AS count
    FROM latest_active_settings s, UNNEST(s.target_locations) AS loc
    WHERE loc.city IS NOT NULL
      AND loc.state IS NOT NULL
    GROUP BY loc.city, loc.state
    ORDER BY count DESC
    LIMIT {limit}
    """
    return run_query(sql)


def get_location_role_combinations(limit=500, start_date=None, end_date=None):
    """Get top location x role combinations by user count."""
    sql = f"""
    WITH {_latest_settings_snapshot_cte()},
    {_latest_active_settings_cte()}
    SELECT
        CONCAT(loc.city, ', ', loc.state) AS location,
        loc.city,
        loc.state,
        r.alias AS role,
        COUNT(DISTINCT s.user_id) AS users
    FROM latest_active_settings s,
    UNNEST(s.target_locations) AS loc,
    UNNEST(s.target_roles_ref) AS r
    WHERE loc.city IS NOT NULL
      AND loc.state IS NOT NULL
      AND r.alias IS NOT NULL
    GROUP BY loc.city, loc.state, r.alias
    ORDER BY users DESC
    LIMIT {limit}
    """
    return run_query(sql)


def get_remote_preference_stats(start_date=None, end_date=None):
    """Get remote vs location-specific user counts."""
    sql = f"""
    WITH {_latest_settings_snapshot_cte()},
    {_latest_active_settings_cte()}
    SELECT
        CASE
            WHEN open_to_remote = TRUE AND open_to_any_city = TRUE THEN 'Remote + Any City'
            WHEN open_to_remote = TRUE THEN 'Remote + Specific Cities'
            WHEN open_to_any_city = TRUE THEN 'Any City (Not Remote)'
            ELSE 'Specific Cities Only'
        END AS preference,
        COUNT(*) AS count
    FROM latest_active_settings
    GROUP BY preference
    ORDER BY count DESC
    """
    return run_query(sql)


def get_target_location_performance(limit=50, start_date=None, end_date=None, match_source="all"):
    """Get target location funnel performance by user cohort."""
    settings_full = get_full_table("user_job_match_settings")
    sql = f"""
    WITH {_latest_settings_snapshot_cte()},
    {_latest_active_settings_cte()},
    {_filtered_matches_cte(start_date=start_date, end_date=end_date, match_source=match_source)},
    match_users AS (
        SELECT
            m.uuid,
            s.user_id,
            m.status,
            m.cpa
        FROM filtered_matches m
        JOIN `{settings_full}` s
          ON m.user_job_match_settings_uuid = s.uuid
        WHERE s.user_id IS NOT NULL
    ),
    location_users AS (
        SELECT DISTINCT
            s.user_id,
            CONCAT(loc.city, ', ', loc.state) AS location
        FROM latest_active_settings s, UNNEST(s.target_locations) AS loc
        WHERE loc.city IS NOT NULL
          AND loc.state IS NOT NULL
    ),
    user_funnel AS (
        SELECT
            lu.location,
            lu.user_id,
            COUNT(m.uuid) AS total_matches,
            COUNTIF(m.status IN {APPROVED_MATCH_STATUSES}) AS approved_matches,
            COUNTIF(m.status = 'APPLIED') AS applied_matches,
            SUM(CASE WHEN m.status = 'APPLIED' THEN COALESCE(m.cpa, 0) ELSE 0 END) AS applied_cpa
        FROM location_users lu
        LEFT JOIN match_users m
          ON lu.user_id = m.user_id
        GROUP BY lu.location, lu.user_id
    )
    SELECT
        location,
        COUNT(DISTINCT user_id) AS users,
        COUNTIF(total_matches > 0) AS users_with_match,
        COUNTIF(approved_matches > 0) AS users_with_approved_match,
        COUNTIF(applied_matches > 0) AS users_with_application,
        SUM(total_matches) AS total_matches,
        SUM(approved_matches) AS approved_matches,
        SUM(applied_matches) AS applied_matches,
        SUM(applied_cpa) AS realized_cpa,
        SAFE_DIVIDE(COUNTIF(total_matches > 0), COUNT(DISTINCT user_id)) AS match_user_rate,
        SAFE_DIVIDE(COUNTIF(approved_matches > 0), COUNTIF(total_matches > 0)) AS approved_user_rate_after_match,
        SAFE_DIVIDE(COUNTIF(applied_matches > 0), COUNTIF(approved_matches > 0)) AS application_user_rate_after_approval,
        SAFE_DIVIDE(SUM(applied_cpa), NULLIF(SUM(applied_matches), 0)) AS avg_cpa_per_application
    FROM user_funnel
    GROUP BY location
    ORDER BY users DESC, users_with_match DESC
    LIMIT {limit}
    """
    return run_query(sql)


def get_active_match_user_signup_location_trends(grain="month", months_back=3):
    """Get current active match-user intake trends by latest target location."""
    user_full = get_full_table("user")
    bucket_expr = (
        "DATE_TRUNC(DATE(u.created_at), WEEK(MONDAY))"
        if str(grain).lower() == "week"
        else "DATE_TRUNC(DATE(u.created_at), MONTH)"
    )
    sql = f"""
    WITH {_latest_settings_snapshot_cte()},
    {_latest_active_settings_cte()},
    signup_locations AS (
        SELECT DISTINCT
            s.user_id,
            {bucket_expr} AS cohort_period,
            CONCAT(loc.city, ', ', loc.state) AS location
        FROM latest_active_settings s
        JOIN `{user_full}` u
          ON s.user_id = u.id
        CROSS JOIN UNNEST(s.target_locations) AS loc
        WHERE loc.city IS NOT NULL
          AND loc.state IS NOT NULL
          AND DATE(u.created_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL {int(months_back)} MONTH)
          AND DATE(u.created_at) <= CURRENT_DATE()
    )
    SELECT
        cohort_period,
        location,
        COUNT(DISTINCT user_id) AS active_match_users
    FROM signup_locations
    GROUP BY cohort_period, location
    ORDER BY cohort_period, active_match_users DESC, location
    """
    return run_query(sql)


def get_location_role_funnel(limit=100, start_date=None, end_date=None, match_source="all"):
    """Get location x role target cohorts and user-level funnel conversion."""
    settings_full = get_full_table("user_job_match_settings")
    sql = f"""
    WITH {_latest_settings_snapshot_cte()},
    {_latest_active_settings_cte()},
    {_filtered_matches_cte(start_date=start_date, end_date=end_date, match_source=match_source)},
    match_users AS (
        SELECT
            m.uuid,
            s.user_id,
            m.status,
            m.cpa
        FROM filtered_matches m
        JOIN `{settings_full}` s
          ON m.user_job_match_settings_uuid = s.uuid
        WHERE s.user_id IS NOT NULL
    ),
    combo_users AS (
        SELECT DISTINCT
            s.user_id,
            CONCAT(loc.city, ', ', loc.state) AS location,
            r.alias AS role
        FROM latest_active_settings s,
        UNNEST(s.target_locations) AS loc,
        UNNEST(s.target_roles_ref) AS r
        WHERE loc.city IS NOT NULL
          AND loc.state IS NOT NULL
          AND r.alias IS NOT NULL
    ),
    user_funnel AS (
        SELECT
            cu.location,
            cu.role,
            cu.user_id,
            COUNT(m.uuid) AS total_matches,
            COUNTIF(m.status IN {APPROVED_MATCH_STATUSES}) AS approved_matches,
            COUNTIF(m.status = 'APPLIED') AS applied_matches,
            SUM(CASE WHEN m.status = 'APPLIED' THEN COALESCE(m.cpa, 0) ELSE 0 END) AS applied_cpa
        FROM combo_users cu
        LEFT JOIN match_users m
          ON cu.user_id = m.user_id
        GROUP BY cu.location, cu.role, cu.user_id
    )
    SELECT
        location,
        role,
        COUNT(DISTINCT user_id) AS users,
        COUNTIF(total_matches > 0) AS users_with_match,
        COUNTIF(approved_matches > 0) AS users_with_approved_match,
        COUNTIF(applied_matches > 0) AS users_with_application,
        SUM(total_matches) AS total_matches,
        SUM(approved_matches) AS approved_matches,
        SUM(applied_matches) AS applied_matches,
        SUM(applied_cpa) AS realized_cpa,
        SAFE_DIVIDE(COUNTIF(total_matches > 0), COUNT(DISTINCT user_id)) AS match_user_rate,
        SAFE_DIVIDE(COUNTIF(approved_matches > 0), COUNTIF(total_matches > 0)) AS approved_user_rate_after_match,
        SAFE_DIVIDE(COUNTIF(applied_matches > 0), COUNTIF(approved_matches > 0)) AS application_user_rate_after_approval,
        SAFE_DIVIDE(SUM(applied_cpa), NULLIF(SUM(applied_matches), 0)) AS avg_cpa_per_application
    FROM user_funnel
    GROUP BY location, role
    ORDER BY users DESC, users_with_match DESC
    LIMIT {limit}
    """
    return run_query(sql)


# ── Role & Industry ───────────────────────────────────────────────────────────

def get_target_role_performance(limit=50, start_date=None, end_date=None, match_source="all"):
    """Get target role funnel performance by user cohort."""
    settings_full = get_full_table("user_job_match_settings")
    sql = f"""
    WITH {_latest_settings_snapshot_cte()},
    {_latest_active_settings_cte()},
    {_filtered_matches_cte(start_date=start_date, end_date=end_date, match_source=match_source)},
    match_users AS (
        SELECT
            m.uuid,
            s.user_id,
            m.status,
            m.cpa
        FROM filtered_matches m
        JOIN `{settings_full}` s
          ON m.user_job_match_settings_uuid = s.uuid
        WHERE s.user_id IS NOT NULL
    ),
    role_users AS (
        SELECT DISTINCT
            s.user_id,
            r.alias AS role
        FROM latest_active_settings s, UNNEST(s.target_roles_ref) AS r
        WHERE r.alias IS NOT NULL
    ),
    user_funnel AS (
        SELECT
            ru.role,
            ru.user_id,
            COUNT(m.uuid) AS total_matches,
            COUNTIF(m.status IN {APPROVED_MATCH_STATUSES}) AS approved_matches,
            COUNTIF(m.status = 'APPLIED') AS applied_matches,
            SUM(CASE WHEN m.status = 'APPLIED' THEN COALESCE(m.cpa, 0) ELSE 0 END) AS applied_cpa
        FROM role_users ru
        LEFT JOIN match_users m
          ON ru.user_id = m.user_id
        GROUP BY ru.role, ru.user_id
    )
    SELECT
        role,
        COUNT(DISTINCT user_id) AS users,
        COUNTIF(total_matches > 0) AS users_with_match,
        COUNTIF(approved_matches > 0) AS users_with_approved_match,
        COUNTIF(applied_matches > 0) AS users_with_application,
        SUM(total_matches) AS total_matches,
        SUM(approved_matches) AS approved_matches,
        SUM(applied_matches) AS applied_matches,
        SUM(applied_cpa) AS realized_cpa,
        SAFE_DIVIDE(COUNTIF(total_matches > 0), COUNT(DISTINCT user_id)) AS match_user_rate,
        SAFE_DIVIDE(COUNTIF(approved_matches > 0), COUNTIF(total_matches > 0)) AS approved_user_rate_after_match,
        SAFE_DIVIDE(COUNTIF(applied_matches > 0), COUNTIF(approved_matches > 0)) AS application_user_rate_after_approval,
        SAFE_DIVIDE(SUM(applied_cpa), NULLIF(SUM(applied_matches), 0)) AS avg_cpa_per_application
    FROM user_funnel
    GROUP BY role
    ORDER BY users DESC, users_with_match DESC
    LIMIT {limit}
    """
    return run_query(sql)


def get_role_location_funnel(limit=100, start_date=None, end_date=None, match_source="all"):
    """Get role x location target cohorts and user-level funnel conversion."""
    return get_location_role_funnel(
        limit=limit,
        start_date=start_date,
        end_date=end_date,
        match_source=match_source,
    )


def get_industry_distribution(start_date=None, end_date=None):
    """Get industry preference counts."""
    sql = f"""
    WITH {_latest_settings_snapshot_cte()},
    {_latest_active_settings_cte()}
    SELECT i.name AS industry, COUNT(*) AS count
    FROM latest_active_settings s, UNNEST(s.target_industries) AS i
    WHERE i.name IS NOT NULL
    GROUP BY i.name
    ORDER BY count DESC
    """
    return run_query(sql)


def get_industry_coverage_with_dates(start_date=None, end_date=None):
    """Get per-user industry coverage with created_at for client-side date filtering."""
    sql = f"""
    WITH {_latest_settings_snapshot_cte()},
    {_latest_active_settings_cte()}
    SELECT
        user_id,
        created_at AS settings_created_at,
        CASE WHEN ARRAY_LENGTH(target_industries) > 0 THEN TRUE ELSE FALSE END AS has_industry,
        CASE WHEN minimum_pay IS NOT NULL AND minimum_pay > 0 THEN TRUE ELSE FALSE END AS has_minimum_pay
    FROM latest_active_settings
    """
    return run_query(sql)


def get_industry_user_mapping(start_date=None, end_date=None):
    """Get per-user industry assignments with user details."""
    user_full = get_full_table("user")
    sql = f"""
    WITH {_latest_settings_snapshot_cte()},
    {_latest_active_settings_cte()}
    SELECT
        s.user_id,
        u.name AS user_name,
        u.first_name,
        u.last_name,
        s.status,
        s.strategy,
        s.experience_level,
        s.created_at AS settings_created_at,
        i.name AS industry,
        (SELECT STRING_AGG(r.alias, ', ') FROM UNNEST(s.target_roles_ref) AS r) AS target_roles,
        (SELECT STRING_AGG(CONCAT(loc.city, ', ', loc.state), ' | ') FROM UNNEST(s.target_locations) AS loc) AS target_locations
    FROM latest_active_settings s
    JOIN `{user_full}` u ON s.user_id = u.id,
    UNNEST(s.target_industries) AS i
    WHERE i.name IS NOT NULL
    ORDER BY i.name, u.name
    """
    return run_query(sql)


def get_role_distribution(limit=30, start_date=None, end_date=None):
    """Get top role preference counts."""
    sql = f"""
    WITH {_latest_settings_snapshot_cte()},
    {_latest_active_settings_cte()}
    SELECT r.alias AS role, COUNT(*) AS count
    FROM latest_active_settings s, UNNEST(s.target_roles_ref) AS r
    WHERE r.alias IS NOT NULL
    GROUP BY r.alias
    ORDER BY count DESC
    LIMIT {limit}
    """
    return run_query(sql)


def get_role_alias_selection_summary():
    """Get current active-user counts with and without a target role alias selected."""
    sql = f"""
    WITH {_latest_settings_snapshot_cte()},
    {_latest_active_settings_cte()},
    role_alias_presence AS (
        SELECT
            s.user_id,
            COUNTIF(r.alias IS NOT NULL AND TRIM(r.alias) != '') AS alias_count
        FROM latest_active_settings s
        LEFT JOIN UNNEST(s.target_roles_ref) AS r
        GROUP BY s.user_id
    )
    SELECT
        COUNT(*) AS active_match_users,
        COUNTIF(alias_count > 0) AS users_with_target_role_alias,
        COUNTIF(alias_count = 0) AS users_without_target_role_alias,
        SAFE_DIVIDE(COUNTIF(alias_count = 0), COUNT(*)) AS users_without_target_role_alias_rate
    FROM role_alias_presence
    """
    return run_query(sql)


def get_certification_distribution(limit=20, start_date=None, end_date=None):
    """Get top certification counts."""
    sql = f"""
    WITH {_latest_settings_snapshot_cte()},
    {_latest_active_settings_cte()}
    SELECT c.name AS certification, COUNT(*) AS count
    FROM latest_active_settings s, UNNEST(s.target_certifications) AS c
    WHERE c.name IS NOT NULL
    GROUP BY c.name
    ORDER BY count DESC
    LIMIT {limit}
    """
    return run_query(sql)


# ── Match Timing ──────────────────────────────────────────────────────────────

def get_match_timing_stats(start_date=None, end_date=None, match_source="all"):
    """Get average time-to-approval and time-to-application by version."""
    sql_start, sql_end = _resolve_match_window(start_date, end_date)
    sql = f"""
    WITH {_filtered_matches_cte(start_date=sql_start, end_date=sql_end, match_source=match_source)}
    SELECT
        IFNULL(match_generation_version, 'unknown') AS version,
        COUNT(*) AS total,
        AVG(CASE WHEN user_approved_at IS NOT NULL
            THEN TIMESTAMP_DIFF(user_approved_at, created_at, HOUR) END) AS avg_hours_to_approval,
        AVG(CASE WHEN applied_at IS NOT NULL AND user_approved_at IS NOT NULL
            THEN TIMESTAMP_DIFF(applied_at, user_approved_at, HOUR) END) AS avg_hours_to_application
    FROM filtered_matches
    GROUP BY version
    ORDER BY total DESC
    """
    return run_query(sql)


def get_match_volume_by_hour(start_date=None, end_date=None, match_source="all"):
    """Get match creation volume by hour of day."""
    sql_start, sql_end = _resolve_match_window(start_date, end_date, days=90)
    sql = f"""
    WITH {_filtered_matches_cte(start_date=sql_start, end_date=sql_end, match_source=match_source)}
    SELECT
        EXTRACT(HOUR FROM created_at) AS hour,
        COUNT(*) AS count
    FROM filtered_matches
    GROUP BY hour
    ORDER BY hour
    """
    return run_query(sql)


def get_match_volume_by_dow(start_date=None, end_date=None, match_source="all"):
    """Get match creation volume by day of week."""
    sql_start, sql_end = _resolve_match_window(start_date, end_date, days=90)
    sql = f"""
    WITH {_filtered_matches_cte(start_date=sql_start, end_date=sql_end, match_source=match_source)}
    SELECT
        EXTRACT(DAYOFWEEK FROM created_at) AS dow,
        CASE EXTRACT(DAYOFWEEK FROM created_at)
            WHEN 1 THEN 'Sunday' WHEN 2 THEN 'Monday' WHEN 3 THEN 'Tuesday'
            WHEN 4 THEN 'Wednesday' WHEN 5 THEN 'Thursday' WHEN 6 THEN 'Friday'
            WHEN 7 THEN 'Saturday'
        END AS day_name,
        COUNT(*) AS count
    FROM filtered_matches
    GROUP BY dow, day_name
    ORDER BY dow
    """
    return run_query(sql)


def get_match_version_over_time(days=90, start_date=None, end_date=None, match_source="all"):
    """Get match generation version distribution over time."""
    sql_start, sql_end = _resolve_match_window(start_date, end_date, days=days)
    sql = f"""
    WITH {_filtered_matches_cte(start_date=sql_start, end_date=sql_end, match_source=match_source)}
    SELECT
        DATE(created_at) AS date,
        IFNULL(match_generation_version, 'unknown') AS version,
        COUNT(*) AS count
    FROM filtered_matches
    GROUP BY date, version
    ORDER BY date
    """
    return run_query(sql)


# ── Contractor Performance ────────────────────────────────────────────────────

def get_contractor_performance(start_date=None, end_date=None, match_source="all"):
    """Get per-contractor stats."""
    sql_start, sql_end = _resolve_match_window(start_date, end_date)
    sql = f"""
    WITH {_filtered_matches_cte(start_date=sql_start, end_date=sql_end, match_source=match_source)}
    SELECT
        assignedUserId AS contractor_id,
        COUNT(*) AS total_assigned,
        COUNTIF(status = 'APPLIED') AS applied,
        COUNTIF(status = 'APP_FAILED') AS failed,
        COUNTIF(status = 'CONTRACTOR_PENDING') AS pending,
        SAFE_DIVIDE(COUNTIF(status = 'APPLIED'), COUNTIF(status IN ('APPLIED', 'APP_FAILED', 'CONTRACTOR_PENDING'))) AS conversion_rate,
        AVG(CASE WHEN applied_at IS NOT NULL AND user_approved_at IS NOT NULL
            THEN TIMESTAMP_DIFF(applied_at, user_approved_at, HOUR) END) AS avg_hours_to_apply
    FROM filtered_matches
    WHERE assignedUserId IS NOT NULL
      AND assignedUserId != ''
    GROUP BY contractor_id
    ORDER BY total_assigned DESC
    """
    return run_query(sql)
