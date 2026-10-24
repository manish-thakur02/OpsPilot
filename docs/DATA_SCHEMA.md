# Authoritative data schema

Generated from the actual UTF-8 inputs by `python -m scripts.inspect_data --write-schema`. The command without that flag is read-only.

Validated population: 141,712 observations and 24,918 unique incidents. Empty cells are unknown information and become SQL NULL; no imputation. Boolean strings True/False become INTEGER 1/0. Date fields remain ISO TEXT with no assumed timezone. Durations are REAL hours.

## incident_events_clean.csv

| Exact column | SQLite type |
|---|---|
| `source_row_id` | INTEGER |
| `number` | TEXT |
| `incident_state` | TEXT |
| `active` | INTEGER |
| `reassignment_count` | INTEGER |
| `reopen_count` | INTEGER |
| `sys_mod_count` | INTEGER |
| `made_sla` | INTEGER |
| `caller_id` | TEXT |
| `opened_by` | TEXT |
| `opened_at` | TEXT |
| `sys_created_by` | TEXT |
| `sys_created_at` | TEXT |
| `sys_updated_by` | TEXT |
| `sys_updated_at` | TEXT |
| `contact_type` | TEXT |
| `location` | TEXT |
| `category` | TEXT |
| `subcategory` | TEXT |
| `u_symptom` | TEXT |
| `cmdb_ci` | TEXT |
| `impact` | TEXT |
| `urgency` | TEXT |
| `priority` | TEXT |
| `assignment_group` | TEXT |
| `assigned_to` | TEXT |
| `knowledge` | INTEGER |
| `u_priority_confirmation` | INTEGER |
| `notify` | TEXT |
| `problem_id` | TEXT |
| `rfc` | TEXT |
| `vendor` | TEXT |
| `caused_by` | TEXT |
| `closed_code` | TEXT |
| `resolved_by` | TEXT |
| `resolved_at` | TEXT |
| `closed_at` | TEXT |
| `incident_state_clean` | TEXT |
| `incident_state_unknown` | INTEGER |

## incident_summary.csv

| Exact column | SQLite type |
|---|---|
| `number` | TEXT |
| `source_row_id` | INTEGER |
| `latest_observed_incident_state_raw` | TEXT |
| `active` | INTEGER |
| `reassignment_count` | INTEGER |
| `reopen_count` | INTEGER |
| `sys_mod_count` | INTEGER |
| `latest_observed_made_sla_raw` | INTEGER |
| `caller_id` | TEXT |
| `opened_by` | TEXT |
| `opened_at` | TEXT |
| `sys_created_by` | TEXT |
| `sys_created_at` | TEXT |
| `sys_updated_by` | TEXT |
| `sys_updated_at` | TEXT |
| `contact_type` | TEXT |
| `location` | TEXT |
| `category` | TEXT |
| `subcategory` | TEXT |
| `u_symptom` | TEXT |
| `cmdb_ci` | TEXT |
| `impact` | TEXT |
| `urgency` | TEXT |
| `latest_observed_priority` | TEXT |
| `assignment_group` | TEXT |
| `assigned_to` | TEXT |
| `knowledge` | INTEGER |
| `u_priority_confirmation` | INTEGER |
| `notify` | TEXT |
| `problem_id` | TEXT |
| `rfc` | TEXT |
| `vendor` | TEXT |
| `caused_by` | TEXT |
| `closed_code` | TEXT |
| `resolved_by` | TEXT |
| `resolved_at` | TEXT |
| `closed_at` | TEXT |
| `latest_observed_incident_state_clean` | TEXT |
| `incident_state_unknown` | INTEGER |
| `matching_rows_at_latest_selection_key` | INTEGER |
| `latest_selection_tied` | INTEGER |
| `event_count` | INTEGER |
| `first_observed_update_at` | TEXT |
| `last_observed_update_at` | TEXT |
| `first_observed_priority` | TEXT |
| `first_observed_made_sla_raw` | INTEGER |
| `priority_distinct_count` | INTEGER |
| `made_sla_distinct_count` | INTEGER |
| `priority_changed` | INTEGER |
| `made_sla_changed` | INTEGER |
| `resolution_hours_latest_record` | REAL |
| `resolution_before_open_flag` | INTEGER |

## latest_selection_ties.csv

| Exact column | SQLite type |
|---|---|
| `number` | TEXT |
| `source_row_id` | INTEGER |
| `sys_updated_at` | TEXT |
| `sys_mod_count` | INTEGER |
| `matching_rows_at_latest_selection_key` | INTEGER |
| `latest_observed_priority` | TEXT |
| `latest_observed_made_sla_raw` | INTEGER |

## Files, keys and relationships

`incident_events_clean.csv`: one row per source observation; primary key source_row_id. number references incident_summary.number (many observations to one incident).

`incident_summary.csv`: primary key number; source_row_id references the selected event of the same incident. Latest selection orders sys_updated_at, numeric sys_mod_count, then numeric source_row_id. It is an observed snapshot, not independently verified final ground truth.

`latest_selection_ties.csv`: audit rows for incidents with multiple latest timestamp/update-count matches. Currently header-only (zero ties), retained as an empty table.

`data_quality_report.json`: provenance, missing-value statistics, row counts, unknown-state diagnostics, semantic limitations, and output manifest. Its original source_file is provenance from another machine, not an input dependency.

## Actual categories

Priorities: 1 - Critical, 2 - High, 3 - Moderate, 4 - Low.

Normalized states: Active, Awaiting Evidence, Awaiting Problem, Awaiting User Info, Awaiting Vendor, Closed, New, Resolved, Unknown.

## Metric definitions and limitations

Incident counts, priority/state distributions, assignment groups and opening trends use the summary table. Trend periods are calendar months of summary opened_at; date filters are inclusive opening dates. Event counts count all observations, including repeated observations. Observed priority/SLA-field changes count distinct values per incident. Observed reopenings count incidents whose maximum recorded reopen_count exceeds zero. Average events divides observations by incidents in the selected population. Resolution duration uses only nonmissing, nonnegative latest-summary durations; report the denominator and exclusions. No duration is a forecast or an as-of measure.

made_sla remains a source Boolean: neither value is labelled breach/compliance. The five raw -100 states are flagged Unknown. Missing data is intentional; 1,556 summaries lack resolution durations. resolved_at and closed_at may contain future completion information even in early observations; no historical/as-of metrics are implemented. No timezone is established. The dataset contains anonymized structured fields, not real narratives or organizational policy. Synthetic demonstration policy does not establish historical compliance.

## Input SHA-256

- `incident_events_clean.csv`: `bba093d54131c49b5ecf52a045e6f20e49779f5995e61a61a00b69aa9d01271d`
- `incident_summary.csv`: `c81c6b4955356f141fb144c89c35a16a5f3655b8261cb218ced6216a5bc14475`
- `latest_selection_ties.csv`: `0d76cc0917b593a680d74632224c10db8a6fa2ef793940d6c6cf5f2d168311f4`
- `data_quality_report.json`: `2cb63708d24e74aa3162838037df32c9f77be0b6ecaa17ef7fc92e7ed77aac33`
