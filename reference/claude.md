# Bandana Job Match Program — Data Reference

## Program Overview

Bandana's Job Match program connects job seekers with opportunities through a semi-automated pipeline. The flow works as follows:

1. **User signs up** on Bandana and enters the Job Match onboarding flow.
2. **User fills out settings/preferences** — target roles, locations, industries, pay, education, certifications, and demographic info (for EEO compliance on applications).
3. **Matches are generated** — either instantly during onboarding (~60–80 seconds) or via a daily cron job that processes ~32,000 users in three priority tiers (active users first, then previously active, then never-active).
4. **User reviews matches** in the Bandana app, approving or rejecting each one.
5. **Contractors apply** on the user's behalf to approved matches. Contractors are assigned via the internal tools at internal.bandana.com and manually submit applications to employers.

Job postings come from two sources: Bandana-created listings and external XML job feeds (aggregated from third-party providers with CPC/CPA pricing models). The match generation algorithm considers user preferences (roles, location, pay, experience, education) against available postings.

---

## Database Tables

There are **6 tables** in the Job Match data model:

| Table | Purpose |
|-------|---------|
| `job_postings` | All job listings — both Bandana-native and those created from XML feed data |
| `user` | Core user/account table for all Job Match users — includes anyone who has signed up for Match, is in draft/onboarding state, or is no longer active in the program |
| `user_job_match_settings` | A user's Job Match preferences, status, and configuration — one row per user |
| `user_job_match_auto_apply_posting` | A "posting wrapper" that links a job posting (or XML raw job) to the auto-apply system |
| `user_job_match_auto_apply_posting_match` | The actual match record tying a user's settings to a posting — tracks approval status, contractor assignment, and application outcome |
| `xml_job_feed_raw_jobs` | Raw job data ingested from external XML feeds before it's converted into a `job_postings` record |

---

## Table Relationships

```
user.id
  └──→ user_job_match_settings.user_id

user_job_match_settings.uuid
  └──→ user_job_match_auto_apply_posting_match.user_job_match_settings_uuid

user_job_match_auto_apply_posting.uuid
  └──→ user_job_match_auto_apply_posting_match.auto_apply_posting_uuid

user_job_match_auto_apply_posting.posting_uuid
  └──→ job_postings.uuid

user_job_match_auto_apply_posting.xml_raw_job_uuid
  └──→ xml_job_feed_raw_jobs.uuid

xml_job_feed_raw_jobs.job_posting_uuid
  └──→ job_postings.uuid

job_postings.xml_job_uuid
  └──→ xml_job_feed_raw_jobs.uuid
```

**In plain language:** A user has one settings record. Matches join a user's settings to an auto-apply posting. An auto-apply posting wraps either a native job posting or an XML raw job (or both, since XML jobs can be promoted into full job_postings records). The `job_postings` ↔ `xml_job_feed_raw_jobs` link is bidirectional.

---

## Field-by-Field Reference

### `job_postings`

Core job listing data. Each row is one job opportunity.

#### Identifiers & Timestamps
| Column | Type | Description |
|--------|------|-------------|
| `uuid` | STRING | Primary key |
| `created_at` | TIMESTAMP | When the posting was created in Bandana's system |
| `updated_at` | TIMESTAMP | Last modification timestamp |
| `key` | STRING | Human-readable unique key for the posting |
| `slug` | STRING | URL slug for the posting page |
| `webflow_slug` | STRING | Slug used on the Webflow-hosted marketing site |
| `webflow_id` | STRING | Webflow CMS item ID |
| `added_date` | TIMESTAMP | When the job was originally added (may differ from created_at for imported jobs) |
| `expiration_date` | TIMESTAMP | When the posting expires |
| `last_checked_at` | TIMESTAMP | Last time the posting's status/validity was checked |
| `last_updated_at_external` | TIMESTAMP | Last update timestamp from the external source (for XML-sourced jobs) |
| `last_expiry_checked_at` | TIMESTAMP | Last time expiration was verified |
| `job_original_id` | STRING | The job's ID in the original external source system |

#### Job Content & Classification
| Column | Type | Description |
|--------|------|-------------|
| `description` | STRING | Full job description text |
| `role_name` | STRING | Display name for the role (69 unique values, e.g., "Coffee Shop Cashier", "Principal Software Engineer", "Warehouse Associate"). See `job_postings_role_names.csv` for all values. |
| `role_uuid` | STRING | FK to roles reference table |
| `original_role_uuid` | STRING | The role UUID before any reclassification |
| `standard_role_uuid` | STRING | Standardized/canonical role UUID |
| `role_class_type_uuid` | STRING | Links to SOC-style role classification |
| `company_uuid` | STRING | FK to companies table |
| `job_source_uuid` | STRING | FK to job sources (identifies origin/feed) |
| `location_uuid` | STRING | FK to locations table |
| `qualifications` | STRING | Required qualifications (mostly empty; some contain "CDL") |
| `education_level` | STRING | Required education. Values: `2 Years`, `Associate's Degree`, `Bachelor's Degree`, `Doctorate`, `High School Diploma or GED`, `Master's Degree`, `No Requirements` |
| `education_field` | STRING | Required field of study (currently empty across all records) |
| `education_field_uuid` | STRING | FK to education fields reference |
| `experience_level` | STRING | Values: `Entry-Level`, `Mid-Level`, `Senior-Level` |
| `min_exp_years` | FLOAT64 | Minimum years of experience required |
| `remote` | BOOLEAN | Whether the job is remote |
| `training` | BOOLEAN | Whether the job provides training |
| `weekly_hours` | FLOAT64 | Expected hours per week |

#### Compensation
| Column | Type | Description |
|--------|------|-------------|
| `pay_quantity` | FLOAT64 | Raw pay amount as stated in the listing |
| `pay_unit` | STRING | Time unit for pay_quantity. Values: `HOURLY`, `MONTHLY`, `WEEKLY`, `YEARLY` |
| `max_pay_quantity` | FLOAT64 | Upper end of pay range (if given) |
| `pay_per_hour` | FLOAT64 | Normalized hourly rate |
| `pay_per_day` | FLOAT64 | Normalized daily rate |
| `pay_per_week` | FLOAT64 | Normalized weekly rate |
| `pay_per_month` | FLOAT64 | Normalized monthly rate |
| `pay_per_year` | FLOAT64 | Normalized annual rate |
| `pay_per_hour_above_min_wage` | FLOAT64 | How much the hourly pay exceeds minimum wage |
| `pay_needs_recalculation` | BOOLEAN | Flag indicating pay normalization needs to be re-run |
| `tip_percent` | FLOAT64 | Tip percentage (for service jobs) |
| `tip_quantity` | FLOAT64 | Tip amount |
| `commission_quantity` | FLOAT64 | Commission amount |
| `benefits_uuid` | STRING | FK to benefits record |

#### Application Details
| Column | Type | Description |
|--------|------|-------------|
| `app_link` | STRING | URL to apply for the job |
| `app_method` | STRING | How applications are submitted. Values: `DIRECT` (apply directly on Bandana.com), `EMAIL` (send application via email), `LINK` (follow an external app_link to the employer's website). Note: `DIRECT` conceptually corresponds with `direct_apply`, but there may be sync/timing issues — some records have `app_method = DIRECT` while `direct_apply` is NULL. |
| `app_email` | STRING | Email address for email-based applications (9 unique values) |
| `direct_apply` | BOOLEAN | Whether Bandana can apply directly without redirecting. Should align with `app_method = DIRECT`, but NULLs may exist due to timing mismatches between when these fields are set. |
| `easy_apply` | BOOLEAN | Simplified application flow available |
| `email_template` | STRING | Template used for email applications |
| `subject_template` | STRING | Subject line template for email applications |
| `calendar_event` | STRING | JSON object with `name`, `start`, `end`, `location` for interview/event scheduling |

#### Flags & Status
| Column | Type | Description |
|--------|------|-------------|
| `expired` | BOOLEAN | Whether the posting has expired |
| `top_priority` | BOOLEAN | Manually flagged as high-priority |
| `featured` | BOOLEAN | Featured on the platform |
| `sponsored` | BOOLEAN | Paid/sponsored listing |
| `draft` | BOOLEAN | Not yet published |
| `urgently_hiring` | BOOLEAN | Employer marked as urgently hiring |
| `needs_review` | BOOLEAN | Flagged for manual review |
| `blacklisted` | BOOLEAN | Blocked from matching |
| `searchable` | BOOLEAN | Included in search results |
| `unlisted` | BOOLEAN | Hidden from public browsing but still matchable |
| `indexable` | BOOLEAN | Whether the posting should be indexed for search |

#### Search & Indexing
| Column | Type | Description |
|--------|------|-------------|
| `last_job_indexed_at` | TIMESTAMP | Last indexed for job search |
| `last_search_indexed_at` | TIMESTAMP | Last indexed in search system |
| `last_elasticsearch_indexed_at` | TIMESTAMP | Last indexed in Elasticsearch |
| `last_open_search_indexed_at` | TIMESTAMP | Last indexed in OpenSearch |
| `last_semantic_indexed_at` | TIMESTAMP | Last indexed for semantic/vector search |
| `removed_from_open_search_index_at` | TIMESTAMP | When removed from OpenSearch index |
| `prioritize_indexing` | BOOLEAN | Should be indexed with higher priority |
| `needs_elasticsearch_indexing` | BOOLEAN | Queued for Elasticsearch re-indexing |
| `needs_semantic_indexing` | BOOLEAN | Queued for semantic re-indexing |
| `needs_search_validation` | BOOLEAN | Queued for search validation |
| `search_validation_reason` | STRING | Reason for validation (currently empty) |

#### Tracking & Metadata
| Column | Type | Description |
|--------|------|-------------|
| `created_by_user_id` | INT64 | User who created the posting (for Bandana-created jobs) |
| `business_team_uuid` | STRING | Associated business team |
| `primary_photo` | STRING | Photo URL for the listing |
| `hash_matches` | ARRAY | Hash values used for deduplication |
| `frozen_modifications` | STRING | JSON tracking which fields were manually overridden (51 unique patterns) |
| `original_values` | STRING | JSON preserving original field values before modifications (91 unique patterns) |
| `summarization` | STRING | AI-generated summary (currently empty) |
| `terminate_sponsorship_at` | TIMESTAMP | When to end sponsored status |
| `expire_posting_at` | TIMESTAMP | Scheduled expiration time |
| `benji_box_meta_data_uuid` | STRING | FK to Benji Box metadata |
| `xml_job_uuid` | STRING | FK to `xml_job_feed_raw_jobs.uuid` — links to the source XML job if this posting was created from an XML feed |

---

### `user`

Core user account table for all Job Match users — includes anyone who has signed up for Match, is in draft/onboarding state, or is no longer active in the program.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT64 | Primary key (integer, not UUID) |
| `name` | STRING | Full display name |
| `first_name` | STRING | First name |
| `last_name` | STRING | Last name |
| `email_verified` | TIMESTAMP | When email was verified (NULL = unverified) |
| `phone_verified` | TIMESTAMP | When phone was verified (NULL = unverified) |
| `image` | STRING | Profile image URL |
| `image_file_uuid` | STRING | FK to uploaded image file |
| `referred_by` | STRING | Referral source identifier |
| `referrer_id` | INT64 | ID of the user who referred them |
| `neighborhood_uuid` | STRING | FK to neighborhood |
| `place_id` | STRING | Google Places ID for user location |
| `dma_uuid` | STRING | FK to Designated Market Area |
| `current_pay` | FLOAT64 | User's current pay rate |
| `target_pay` | FLOAT64 | User's desired pay rate |
| `target_benefits` | ARRAY | Benefits the user is seeking |
| `subscription_default` | STRING | Default subscription plan |
| `super_admin` | BOOLEAN | Whether the user has admin privileges |
| `internal` | BOOLEAN | Whether this is a Bandana internal/test account |
| `merged_into_user_id` | INT64 | If this account was merged, points to the surviving account |
| `default_resume_id` | STRING | FK to the user's primary resume |
| `enrolled_in_recommendations` | BOOLEAN | Whether the user receives job recommendations |
| `last_login` | TIMESTAMP | Last login time |
| `last_sendgrid_contact_synced_at` | TIMESTAMP | Last time user data was synced to SendGrid (email marketing) |
| `state` | STRING | Account state (currently empty) |
| `created_at` | TIMESTAMP | Account creation time |
| `updated_at` | TIMESTAMP | Last account update |

---

### `user_job_match_settings`

One row per Job Match user. Contains all preferences that drive match generation, plus operational fields for contractor assignment and SMS communication.

#### Identifiers & Status
| Column | Type | Description |
|--------|------|-------------|
| `uuid` | STRING | Primary key |
| `user_id` | INT64 | FK to `user.id` |
| `created_at` | TIMESTAMP | When settings were first created |
| `updated_at` | TIMESTAMP | Last settings update |
| `status` | STRING | Current program status. Values: `ACTIVE` (receiving matches and getting applied), `DRAFT` (incomplete onboarding), `EMAIL_ONLY` (only receives email notifications), `INTERESTED` (expressed interest but not fully enrolled), `LATER` (deferred enrollment), `PAUSED` (temporarily stopped), `PENDING` (awaiting activation) |
| `strategy` | STRING | Match strictness. Values: `BALANCED` (moderate filtering), `OPEN` (broader matches), `PAY` (prioritize compensation), `STRICT` (tight criteria matching) |
| `over_eighteen` | BOOLEAN | Age verification |

#### Job Preferences
| Column | Type | Description |
|--------|------|-------------|
| `minimum_pay` | FLOAT64 | Minimum acceptable pay |
| `target_roles` | ARRAY\<STRING\> | Legacy: flat array of role name strings |
| `target_roles_ref` | ARRAY\<STRUCT\<alias, uuid\>\> | Preferred roles with structured references. The `alias` field maps to values in `target_roles_ref.csv` (1,375 unique role aliases like "Accountant", "Barista", "Software Engineer") |
| `target_locations` | ARRAY\<STRUCT\<neighborhood, street, zipcode, state, lat, long, city, uuid, country\>\> | Where the user wants to work. Cities/states drawn from `target_locations.csv` (5,733 city/state/country combos) |
| `target_industries` | ARRAY\<STRUCT\<name, uuid\>\> | Preferred industries. Names from `target_industries.csv` (17 industries: Biotechnology, Construction, Culture & Entertainment, Delivery & Transportation, Education, Financial Services, Fitness & Clubs, Food & Bars, Government, Healthcare & Mental Health, Hotels & Accommodation, Manufacturing, Non-Profit & Public Service, Pharmacy, Retail & Wholesale, Staffing Group, Technology) |
| `target_certifications` | ARRAY\<STRUCT\<name, uuid\>\> | Certifications the user holds. Names from `target_certifications.csv` (105 certifications) |
| `target_job_type` | STRING | Desired job type (1,484 unique values — likely free-text or semi-structured) |
| `target_benefits` | ARRAY\<STRING\> | Desired benefits |
| `target_boroughs` | ARRAY\<STRING\> | Legacy: NYC borough preferences |
| `target_transit_lines` | ARRAY\<STRUCT\<name, uuid\>\> | Transit lines the user can access (NYC-specific) |
| `target_neighborhoods` | ARRAY\<STRUCT\<name, city, uuid\>\> | Preferred neighborhoods |
| `target_role_class` | ARRAY\<STRUCT\<major_group, minor_group, broad_group, uuid\>\> | SOC-style occupational classification preferences |
| `open_to_any_city` | BOOLEAN | Willing to work in any city |
| `open_to_hybrid` | BOOLEAN | Open to hybrid work |
| `open_to_remote` | BOOLEAN | Open to remote work |
| `able_to_drive` | BOOLEAN | Can commute by car |
| `raw_notion_locations` | ARRAY | Legacy: location data imported from Notion |

#### Education
| Column | Type | Description |
|--------|------|-------------|
| `education_level` | STRING | Highest education achieved. Values: `Associate's`, `Associate's Degree`, `Bachelor's`, `Bachelor's Degree`, `Doctorate`, `High School Diploma or GED`, `High school / GED`, `Master's Degree`, `No Requirements`. Note: some inconsistency in naming (e.g., "Associate's" vs "Associate's Degree") |
| `education_field` | STRING | Legacy: field of study (only 2 values seen: "Film & TV", "Humanities and Social Science") |
| `education_gpa` | STRING | GPA (currently empty) |
| `target_education_fields` | ARRAY\<STRUCT\<name, jms_uuid, education_level\>\> | Structured education preferences. Names and levels from `target_education_fields.csv` (412 field+degree combos across Associate's, Bachelor's, Master's, Doctorate) |
| `experience_level` | STRING | Values: `Entry-Level`, `Mid-Level`, `Senior-Level` |

#### EEO / Demographic Fields
These fields exist to auto-fill Equal Employment Opportunity questions on job applications submitted by contractors.

| Column | Type | Description |
|--------|------|-------------|
| `race` | STRING | Values: `American Indian or Alaska Native`, `Asian`, `Black or African American`, `Hispanic or Latino`, `Native Hawaiian or Other Pacific Islander`, `Two or more races`, `White`, `Rather Not Disclosed`, and a few other variants (11 total) |
| `gender` | STRING | Values: `Female`, `Male`, or empty |
| `is_disabled` | STRING | Values: `DECLINE`, `NO`, `YES` |
| `is_veteran` | STRING | Values: `DECLINE`, `NO`, `YES` |
| `needs_sponsorship` | STRING | Visa sponsorship needed. Values: `NO`, `YES` |

#### Resume & Application
| Column | Type | Description |
|--------|------|-------------|
| `resume_link` | STRING | URL to the user's resume |
| `user_subscription_uuid` | STRING | FK to subscription record |

#### Contractor & Operations
| Column | Type | Description |
|--------|------|-------------|
| `assigned_user_id` | STRING | ID of the contractor assigned to handle this user's applications |
| `contractor_status` | STRING | Values: `CONTRACTOR_COMPLETE` (contractor finished all pending apps), `NEEDS_CONTRACTOR` (awaiting contractor assignment) |
| `internal_notes` | STRING | Free-text notes from Bandana staff |
| `last_job_match_activity_at` | TIMESTAMP | Last time the user interacted with matches (approved, rejected, etc.) |

#### SMS / Sendblue Communication
| Column | Type | Description |
|--------|------|-------------|
| `sms_enabled` | BOOLEAN | User has opted into SMS |
| `enrolled_in_sendblue` | BOOLEAN | Active in the Sendblue SMS system |
| `sendblue_activity_status` | STRING | Current SMS engagement state. Values: `ACTIVE_FOLLOWUP` (in active follow-up sequence), `INACTIVE` (not engaging), `INACTIVITY_REMINDER` (sent a re-engagement reminder), `INTRO_PENDING` (initial intro message not yet sent) |
| `follow_up_sent_at` | TIMESTAMP | When last follow-up was sent |
| `sendblue_follow_up_started_at` | TIMESTAMP | When follow-up sequence began |
| `follow_up_template` | STRING | Template used for follow-up messages |

---

### `user_job_match_auto_apply_posting`

A wrapper around a job posting that makes it eligible for the auto-apply system. One record per unique job that has been surfaced to any user as a match.

| Column | Type | Description |
|--------|------|-------------|
| `uuid` | STRING | Primary key |
| `created_at` | TIMESTAMP | When this auto-apply posting was created |
| `updated_at` | TIMESTAMP | Last update |
| `posting_uuid` | STRING | FK to `job_postings.uuid` — the underlying Bandana job posting |
| `xml_raw_job_uuid` | STRING | FK to `xml_job_feed_raw_jobs.uuid` — the underlying XML feed job (may exist alongside or instead of posting_uuid) |
| `canonical_app_link` | STRING | The definitive application URL to use |
| `tags` | ARRAY | Tags/labels applied to this posting in the auto-apply context |
| `contractor_instructions` | STRING | Free-text instructions for the contractor on how to apply (223 unique instruction sets) |
| `needs_verification_code` | BOOLEAN | Whether the application requires an email/phone verification code |

---

### `user_job_match_auto_apply_posting_match`

The core match table. Each row is one user matched to one job. This is where you track the full lifecycle from match generation → user decision → contractor application → outcome.

| Column | Type | Description |
|--------|------|-------------|
| `uuid` | STRING | Primary key |
| `created_at` | TIMESTAMP | When the match was generated |
| `updated_at` | TIMESTAMP | Last update |
| `auto_apply_posting_uuid` | STRING | FK to `user_job_match_auto_apply_posting.uuid` |
| `user_job_match_settings_uuid` | STRING | FK to `user_job_match_settings.uuid` |
| `status` | STRING | Match lifecycle status. Values: `USER_PENDING` (awaiting user review), `USER_APPROVED` (user approved, awaiting contractor), `USER_REJECTED` (user declined), `CONTRACTOR_PENDING` (assigned to contractor, application in progress), `APPLIED` (contractor successfully submitted application), `APP_FAILED` (application attempt failed), `ACCOUNT_EXISTS` (user already has an account on the employer's site), `JOB_EXPIRED` (job expired before application could be submitted) |
| `user_approved_at` | TIMESTAMP | When the user approved this match |
| `user_rejected_at` | TIMESTAMP | When the user rejected this match |
| `applied_at` | TIMESTAMP | When the application was successfully submitted |
| `assignedUserId` | STRING | ID of the contractor assigned to this specific match (40 unique contractor IDs in the dataset) |
| `cpa` | FLOAT64 | Cost-per-application — what Bandana earns/pays for this application (relevant for XML feed jobs with CPA pricing) |
| `contractornotes` | STRING | Notes from the contractor about the application process |
| `ipAddressUuid` | STRING | IP address used during application (15,732 unique — used for fraud detection / compliance) |
| `job_posting_application_uuid` | STRING | FK to the detailed application record |
| `creator_id` | STRING | Who/what created this match (system or manual) |
| `match_generation_version` | STRING | Which algorithm generated this match. Values: `instant` (generated during user onboarding, ~60-80 sec), `v1` (first version of daily cron), `v2` (improved daily cron algorithm) |
| `hidden` | BOOLEAN | Whether this match is hidden from the user's view |
| `hide_match_at` | TIMESTAMP | Scheduled time to hide the match |

---

### `xml_job_feed_raw_jobs`

Raw job data from external XML feeds. These records represent jobs as they arrive from third-party aggregators before being cleaned and optionally promoted into `job_postings` records.

#### Identifiers & Source
| Column | Type | Description |
|--------|------|-------------|
| `uuid` | STRING | Primary key |
| `created_at` | TIMESTAMP | When ingested into Bandana |
| `updated_at` | TIMESTAMP | Last update |
| `xml_job_feed_uuid` | STRING | FK to the feed configuration (identifies which partner/aggregator) |
| `job_id` | STRING | Job ID from the external source |
| `last_run_id` | STRING | ID of the feed processing run that last touched this record |
| `organization_id` | STRING | External organization identifier |
| `company_id` | STRING | External company identifier |
| `tenant_id` | STRING | Multi-tenant identifier from the feed |
| `job_posting_uuid` | STRING | FK to `job_postings.uuid` — set when this XML job has been promoted to a full Bandana posting |

#### Job Content
| Column | Type | Description |
|--------|------|-------------|
| `role_name` | STRING | Job title from the feed (2M+ unique values — very noisy/unstandardized) |
| `company_name` | STRING | Employer name (22k unique) |
| `description` | STRING | Full job description |
| `category` | STRING | Job category from the feed (8,480 unique values). Top categories by volume: Healthcare, Nursing, Heavy truck drivers. See `xml_categories.csv` for full list. |
| `category_id` | STRING | External category ID |
| `segment_name` | STRING | Feed segment/cohort name (718 unique). Top segments: Nursing, Clinical, FY26_Field_Operations. See `xml_segment_names.csv` for full list. |
| `requirement` | STRING | Job requirements text (540 unique values) |
| `job_type` | STRING | Employment type (200 unique values — e.g., full-time, part-time, contract) |
| `experience` | STRING | Experience requirement. Values: empty, `0`, `0-1 Year`, `1-2 Years`, `2-3 Years`, `3-5 Years`, `5-7 Years`, `7-10 Years`, `None` |
| `education` | STRING | Education requirement (currently empty across all records) |
| `logo` | STRING | Company logo URL |

#### Location
| Column | Type | Description |
|--------|------|-------------|
| `location` | STRING | Full location string (69k unique) |
| `streetaddress` | STRING | Street address |
| `city` | STRING | City (21k unique) |
| `state` | STRING | State/province (166 unique — includes international) |
| `country` | STRING | Country |
| `zipcode` | STRING | ZIP/postal code (33k unique) |
| `latitude` | FLOAT64 | Latitude |
| `longitude` | FLOAT64 | Longitude |

#### Compensation
| Column | Type | Description |
|--------|------|-------------|
| `pay` | STRING | Raw pay string from the feed (26k unique — very inconsistent formatting) |
| `pay_min` | FLOAT64 | Minimum pay |
| `pay_max` | FLOAT64 | Maximum pay |
| `pay_unit` | STRING | Pay period unit (currently empty) |
| `pay_type` | STRING | Pay type (currently empty) |

#### Monetization
| Column | Type | Description |
|--------|------|-------------|
| `cpc` | FLOAT64 | Cost-per-click — what Bandana pays when a user clicks through to this job |
| `cpa` | FLOAT64 | Cost-per-application — what Bandana earns when an application is submitted |

#### Application & Feed Metadata
| Column | Type | Description |
|--------|------|-------------|
| `app_link` | STRING | Application URL from the feed |
| `branded_link_uuid` | STRING | FK to Bandana's branded/tracked link |
| `posted_date` | TIMESTAMP | When the job was originally posted |
| `expiration_date` | TIMESTAMP | When the job expires |
| `feed_expired` | BOOLEAN | Whether the feed marked this as expired |
| `expired` | BOOLEAN | Whether Bandana considers this expired |
| `status` | STRING | Only value seen: `active` |
| `upsert_status` | STRING | (Currently empty) |
| `mobile_friendly` | BOOLEAN | Whether the application is mobile-friendly |
| `html_jobs` | STRING | HTML content flag |
| `should_prioritize` | BOOLEAN | Feed-level priority flag |
| `needs_verification_step` | BOOLEAN | Whether applying requires a verification step |
| `xml_source_url` | STRING | URL of the XML feed source |
| `extra_data` | STRING | Additional unstructured data from the feed (7,645 unique values) |
| `monitor_for_notification` | BOOLEAN | Whether to monitor this job for notification triggers |
| `additional_clicks_max` | FLOAT64 | Max additional clicks allowed |
| `additional_clicks_min` | FLOAT64 | Min additional clicks |
| `additional_clicks_mode` | STRING | Only value: `replace` |

#### Airtable Integration
| Column | Type | Description |
|--------|------|-------------|
| `airtable_base_id` | STRING | Airtable base ID (for legacy integrations) |
| `airtable_record_id` | STRING | Airtable record ID |
| `airtable_table_id` | STRING | Airtable table ID |

---

## Key Analytical Patterns

### Match Funnel Analysis
To analyze the full funnel from match generation to application outcome, join through the chain:
```
user
  → user_job_match_settings (on user_id)
    → user_job_match_auto_apply_posting_match (on user_job_match_settings_uuid)
      → user_job_match_auto_apply_posting (on auto_apply_posting_uuid)
        → job_postings (on posting_uuid) OR xml_job_feed_raw_jobs (on xml_raw_job_uuid)
```

Track conversion at each stage: `USER_PENDING` → `USER_APPROVED` → `CONTRACTOR_PENDING` → `APPLIED`.

### User Engagement
- `user_job_match_settings.status` tells you if a user is active in the program
- `last_job_match_activity_at` shows recency of engagement
- `sendblue_activity_status` reveals SMS engagement state
- `match_generation_version` indicates whether the user was matched during onboarding (`instant`) or via daily cron (`v1`/`v2`)

### Job Quality & Source Analysis
- Compare match approval rates between native `job_postings` and `xml_job_feed_raw_jobs`-sourced matches
- XML jobs have noisy `role_name` values (2M+ unique) vs. cleaned `job_postings.role_name` (69 unique)
- `xml_job_feed_raw_jobs.segment_name` and `category` can help identify which feed segments produce the best matches
- `cpc` and `cpa` on XML jobs track monetization economics

### Pay Analysis
- `job_postings` has fully normalized pay columns (`pay_per_hour`, `pay_per_day`, etc.)
- `xml_job_feed_raw_jobs` has raw, inconsistently formatted `pay` strings — use `pay_min`/`pay_max` when available
- `user_job_match_settings.minimum_pay` is the user's floor

### Contractor Performance
- `assignedUserId` on matches identifies the contractor
- Track `CONTRACTOR_PENDING` → `APPLIED` conversion rates per contractor
- `contractornotes` may contain useful context on application difficulties
- `contractor_instructions` on auto_apply_postings tells you what the contractor was told to do

---

## Reference Data Files

| File | Rows | Description |
|------|------|-------------|
| `field_reference.csv` | 243 | Master schema: every column across all 6 tables with data types, categories, unique counts, and sample values |
| `target_locations.csv` | 5,733 | All city/state/country options for user location preferences |
| `target_roles_ref.csv` | 1,375 | All job role aliases users can select |
| `target_certifications.csv` | 105 | All certification names |
| `target_industries.csv` | 17 | All industry names |
| `target_education_fields.csv` | 412 | Field-of-study + degree level combinations |
| `job_postings_role_names.csv` | 69 | All distinct role_name values in the job_postings table |
| `xml_categories.csv` | 8,480 | XML feed job categories with record counts |
| `xml_segment_names.csv` | 718 | XML feed segment names with record counts |
