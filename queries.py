"""Predefined SQL query templates for common analysis patterns."""

import config

SCHEMA = f"""
SELECT column_name, data_type, is_nullable
FROM `{config.PROJECT_ID}.{config.DATASET}.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name = @table_name
ORDER BY ordinal_position
"""

ALL_DATA = f"""
SELECT *
FROM `{config.FULL_TABLE}`
ORDER BY {{order_by}}
LIMIT @row_limit
"""

FILTERED_DATA = f"""
SELECT {{columns}}
FROM `{config.FULL_TABLE}`
WHERE {{where_clause}}
ORDER BY {{order_by}}
LIMIT @row_limit
"""

ROW_COUNT = f"""
SELECT COUNT(*) as total_rows
FROM `{config.FULL_TABLE}`
"""

RECENT_ROWS = f"""
SELECT *
FROM `{config.FULL_TABLE}`
WHERE {{timestamp_col}} >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @hours_back HOUR)
ORDER BY {{timestamp_col}} DESC
LIMIT @row_limit
"""

COLUMN_STATS = f"""
SELECT
    COUNT(*) as total_rows,
    COUNT(DISTINCT {{column}}) as unique_values,
    COUNTIF({{column}} IS NULL) as null_count
FROM `{config.FULL_TABLE}`
"""

VALUE_COUNTS = f"""
SELECT {{column}}, COUNT(*) as count
FROM `{config.FULL_TABLE}`
GROUP BY {{column}}
ORDER BY count DESC
LIMIT 50
"""
