-- Migration 004: Enhance scenario_accessibility with status categorization
-- and multi-threshold flags (15, 30, 45 minutes) without duplicating population.

alter table gis.scenario_accessibility
  add column if not exists status_category text not null default 'reachable'
    check (status_category in ('reachable', 'network_unreachable', 'invalid_snap')),
  add column if not exists threshold_15min boolean not null default false,
  add column if not exists threshold_30min boolean not null default false,
  add column if not exists threshold_45min boolean not null default false;

-- Create index on scenario_id and status for fast KPI aggregation
create index if not exists scenario_accessibility_status_idx
  on gis.scenario_accessibility(scenario_id, status_category);
