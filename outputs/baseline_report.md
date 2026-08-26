# COTA Baseline Report

Generated 2026-08-26T01:10:47.098249+00:00

All figures below are **scheduled estimates derived from COTA's published GTFS feed**. They are not COTA's reported operating statistics and have not been reconciled against the National Transit Database.

## DATA RETRIEVAL STATUS

| source                                                                   | publisher                             | status         | retrieved_at                     |
|:-------------------------------------------------------------------------|:--------------------------------------|:---------------|:---------------------------------|
| COTA GTFS static feed                                                    | Central Ohio Transit Authority        | RETRIEVED      | 2026-08-25T23:50:49.250246+00:00 |
| COTA GTFS-Realtime service alerts                                        | COTA / Vontas                         | BLOCKED_EGRESS |                                  |
| COTA GTFS-Realtime trip updates                                          | COTA via Swiftly                      | BLOCKED_EGRESS |                                  |
| COTA GTFS-Realtime vehicle positions                                     | COTA via Swiftly                      | BLOCKED_EGRESS |                                  |
| COTA open GIS data portal                                                | COTA                                  | BLOCKED_EGRESS |                                  |
| National Transit Database agency profile — COTA (NTD ID 50066)           | Federal Transit Administration        | UNKNOWN        |                                  |
| LEHD LODES8 Ohio OD (JT00, main)                                         | US Census Bureau LEHD                 | BLOCKED_EGRESS |                                  |
| LEHD LODES8 Ohio WAC (S000 JT00 2022)                                    | US Census Bureau LEHD                 | RETRIEVED      | 2026-08-26T00:47:18.403181+00:00 |
| LEHD LODES8 Ohio RAC (S000 JT00 2022)                                    | US Census Bureau LEHD                 | RETRIEVED      | 2026-08-26T00:47:18.399973+00:00 |
| 2020 Census block-group population centroids, Ohio                       | US Census Bureau                      | RETRIEVED      | 2026-08-26T00:47:18.404255+00:00 |
| ACS 5-year estimates via Census API                                      | US Census Bureau                      | BLOCKED_EGRESS |                                  |
| MORPC regional traffic count database                                    | Mid-Ohio Regional Planning Commission | UNKNOWN        |                                  |
| ODOT Traffic Count/TDMS data                                             | Ohio DOT                              | UNKNOWN        |                                  |
| COTA planning documents (LinkUS, System Redesign, APC/ridership reports) | COTA                                  | UNKNOWN        |                                  |

`BLOCKED_EGRESS` means the URL is confirmed correct but this sandbox cannot reach the host; the file was retrieved on the operator's machine and registered with full provenance. `UNKNOWN` means no authoritative URL has been located yet.

## GTFS VALIDATION

- errors: **0**
- warnings: **0**

No structural issues found. Checks applied: required fields, unique IDs, trip→route / stop_time→trip / stop_time→stop / trip→service referential integrity, coordinate validity, stop-sequence monotonicity, non-decreasing departure times, calendar presence, shape references.

## NETWORK SUMMARY

- feed version: `2026-MAY-04-BB_20260630`
- representative weekday: **2026-05-26** (modal weekday service pattern; occurs on 45 of the Tue/Wed/Thu dates in the feed window)
- routes with weekday service: **39** (of 42 defined in the feed)
- stops served: **2,949**
- weekday trips: **2,331**
- distinct stop patterns: **111**
- stops served by more than one route (transfer points): **645**

## ROUTE SUMMARY

Top 15 routes by scheduled revenue vehicle-hours:

|   route_id | route_name              |   n_trips |   n_patterns |   span_hours |   mean_runtime_min |   revenue_veh_hours |
|-----------:|:------------------------|----------:|-------------:|-------------:|-------------------:|--------------------:|
|        008 | 8 KARL/S HIGH/PARSONS   |       144 |            4 |        19.93 |              94.95 |              227.88 |
|        002 | 2 E MAIN/N HIGH         |       150 |            4 |        20.1  |              85.99 |              214.98 |
|        001 | 1 KENNY/LIVINGSTON      |       149 |            4 |        20.07 |              86.4  |              214.55 |
|        010 | 10 E BROAD/W BROAD      |       143 |            8 |        20.12 |              80.94 |              192.92 |
|        007 | 7 MT VERNON             |       138 |            6 |        19.95 |              58.05 |              133.52 |
|        101 | CMAX CMAX               |       149 |            4 |        20.45 |              50.79 |              126.13 |
|        005 | 5 W 5TH AVE/REFUGEE     |        74 |            4 |        19.72 |              95.36 |              117.62 |
|        034 | 34 MORSE                |       154 |            2 |        19.8  |              45.19 |              115.98 |
|        022 | 22 OSU-RICKENBACKER     |       107 |            5 |        19.83 |              64.92 |              115.77 |
|        023 | 23 JAMES-STELZER        |       146 |            2 |        18.75 |              44.44 |              108.13 |
|        003 | 3 NORTHWEST/HARRISBURG  |        79 |            3 |        20.2  |              77.95 |              102.63 |
|        004 | 4 INDIANOLA/LOCKBOURNE  |        75 |            3 |        20    |              75.75 |               94.68 |
|        102 | 102 POLARIS PKWY/N HIGH |        74 |            2 |        19.93 |              74.88 |               92.35 |
|        006 | 6 SULLIVANT             |       134 |            2 |        19.35 |              40.7  |               90.9  |
|        024 | 24 HAMILTON RD          |        76 |            2 |        19.68 |              71.45 |               90.5  |

Full table: `data/processed/route_summary.csv` (39 routes).

## STOP SUMMARY

- stops in feed: **2,949**
- stops with weekday service: **2,949**
- mean consecutive-stop spacing, median across routes: **473 m** (1,553 ft)
- spacing range across routes: 295–3,996 m

Spacing is straight-line distance between consecutive stops on each route's most common pattern, computed in EPSG:32617 (metres). It is a lower bound on on-street spacing.

## SERVICE FREQUENCY

| period   |   route_directions |   trips |   median_headway_min |   p25 |   p75 |   min |   max |   trip_weighted_mean |   pct_routes_15min_or_better |
|:---------|-------------------:|--------:|---------------------:|------:|------:|------:|------:|---------------------:|-----------------------------:|
| am_peak  |                 68 |     404 |                29.6  | 15    | 59.75 | 13.64 |   180 |                28.09 |                        26.47 |
| early    |                 46 |     140 |                29    | 15    | 58.25 |  9.4  |   120 |                27.04 |                        28.26 |
| evening  |                 49 |     455 |                30.14 | 17.38 | 56.33 | 14.53 |   240 |                25.46 |                         6.12 |
| midday   |                 50 |     750 |                29.27 | 14.88 | 54.3  | 14.3  |   195 |                24.06 |                        34    |
| owl      |                 44 |     176 |                30    | 16.19 | 30.92 | 11    |   360 |                28.04 |                        20.45 |
| pm_peak  |                 69 |     406 |                30.4  | 15.55 | 60.5  | 13.73 |   180 |                29.26 |                        10.14 |

Headway = mean gap between consecutive first departures of trips on the same route+direction whose first departure falls in the period.

## SERVICE SPAN

- median route span: **19.5 h**
- longest: CMAX CMAX (20.4 h); shortest: 46 GAHANNA (9.7 h)
- system first departure: 4.38 h; last arrival: 25.33 h (hours ≥24 are past-midnight service)

## SCHEDULED RUNTIME

- mean one-way trip runtime: **64.8 min**
- median 66.0 min; p10 39.0; p90 94.0; max 111.0

Runtime = last scheduled arrival − first scheduled departure of a trip.

## APPROXIMATE RESOURCE METRICS

- scheduled **revenue vehicle-hours per weekday: 2,517.2** (Σ trip runtimes; excludes layover, deadhead and pull-out/pull-in)
- scheduled **revenue vehicle-miles per weekday: 38,471**
- peak simultaneously-running scheduled trips: **171** (schedule sweep)

Peak by period (schedule sweep — note these are peaks *within* a window, so early-morning and owl values are dominated by the boundary with the adjacent peak):

| period | peak concurrent trips |
|---|---|
| early | 116 |
| am_peak | 153 |
| midday | 149 |
| pm_peak | 171 |
| evening | 149 |
| owl | 124 |

**Vehicle-mile method check.** `stop_times.shape_dist_traveled` is kilometers in this feed — GTFS does not fix the unit, so it was inferred by comparison against the projected shape geometry. The two independent methods agree to 0.16% (38,471 vs 38,531 miles).

**These are not COTA's reported operating statistics.** Actual fleet requirement additionally depends on layover/recovery, deadhead, interlining across routes (GTFS `block_id` is present but not yet exploited), run-cutting and maintenance spare ratio — none of which are known here.

## AVAILABLE EXTERNAL DEMAND DATA

- LEHD LODES8 (2022) RAC + WAC, Central Ohio counties: **976,504 workers** by residence and **1,086,541 jobs** by workplace across 1,397 block groups
- 2020 Census population-weighted block-group centroids (Ohio)
- within 600 m of a served COTA stop: **368,626 workers (37.7%)** and **571,047 jobs (52.6%)**
- stops receiving allocated demand: 2,432

Documented path: Census block home/work flow → block-group aggregation → population-weighted centroid → distance-decayed allocation to stops within the catchment → per-route boarding potential (a stop's mass is split among the routes serving it, so shared stops are not double-counted) → period split by assumed shares.

**This is a proxy for relative demand, not observed ridership.** LODES covers home→work commuting only, is not transit-mode-specific, and the period split is assumed. It is adequate for ranking where service is worth more; it is not a ridership forecast.

ACS variables identified for future use (not yet retrieved): B01003_001E population; B08301 means of transportation to work (B08301_010E public transit); B08201/B25044 vehicles available (zero-car households); B19013_001E median household income; B23025 employment status; B18101/S1810 disability. No normative demographic weighting is embedded in the optimization.

## AVAILABLE TRAFFIC DATA

| source | status |
|---|---|
| MORPC regional traffic counts | UNKNOWN — portal not reachable from this sandbox; no authoritative direct URL confirmed |
| ODOT TDMS / traffic monitoring | UNKNOWN — same |
| COTA GTFS-Realtime (vehicle positions, trip updates, alerts) | URLs confirmed on cota.com/data; not collected (egress blocked) |

Traffic-count data is not required for Experiment 1 (frequency reallocation on fixed geometry with scheduled runtimes). It becomes necessary when segment runtimes are made congestion-responsive.

## MISSING DATA

| variable | classification | note |
|---|---|---|
| current stop-level boardings/alightings | **REQUIRES PUBLIC RECORDS REQUEST** | COTA operates APC-equipped buses; stop-level boardings are not in any public feed located. Not derivable from GTFS. |
| trip-level APC | **REQUIRES PUBLIC RECORDS REQUEST** | Same source as above; needed to calibrate the demand proxy. |
| driver work rules | **REQUIRES PUBLIC RECORDS REQUEST** | Union agreement (TWU Local 208) governs run length, breaks, spread; may be partly public but not retrieved. |
| operator availability | **LIKELY INTERNAL ONLY** | Headcount, absence and extraboard levels are operational data. |
| maintenance reserve | **ESTIMABLE** | NTD reports fleet size and vehicles operated in max service; the ratio bounds spare ratio. Not yet retrieved in this environment. |
| deadhead rules | **DERIVABLE (partially)** | GTFS block_id is present, so vehicle blocks and the pull-out/pull-in structure are partly reconstructable; depot locations are not in GTFS. |
| depot assignments | **LIKELY INTERNAL ONLY** | COTA garage locations are public; per-block assignment is not. |
| real fuel/energy cost | **PUBLICLY AVAILABLE** | NTD reports annual fuel/energy consumption and operating expense by mode. |
| observed route runtime distributions | **DERIVABLE** | GTFS-Realtime vehicle positions and trip updates are public; sustained collection yields empirical segment travel-time distributions. |
| transfer behavior | **ESTIMABLE** | Fare-system transfer data is internal; transfer rates can be estimated from network structure and a mode-choice model. |
| latent non-work OD demand | **ESTIMABLE** | LODES covers home→work only. Non-work travel needs NHTS rates, a regional travel model (MORPC), or LBS data. |
| service-area population/demographics | **PUBLICLY AVAILABLE** | ACS 5-year at tract/block-group level via the Census API. |

## KNOWN ASSUMPTIONS

| assumption | value | basis |
|---|---|---|
| projected CRS | EPSG:32617 | UTM 17N, metres; all planar distance math |
| service periods | {'early': [4, 6], 'am_peak': [6, 9], 'midday': [9, 15], 'pm_peak': [15, 18], 'evening': [18, 22], 'owl': [22, 28]} | analyst-defined |
| layover/recovery ratio | 15% | industry-typical 10–20%; **not a verified COTA work rule** |
| random-arrival headway threshold | 12 min | standard practice |
| demand retention at long headways | floor 25% at 120 min | assumed elasticity, **uncalibrated** |
| avg passenger ride fraction of route | 35% | typical US bus; **unverified for COTA** |
| transfer rate | 20% | typical mid-size bus system; **COTA's observed rate is UNKNOWN** |
| bus planning capacity | 60 | 40-ft seated+standing |
| demand catchment radius | 600 m | ~5 min walk; assumed |
| period demand shares | {'early': 0.05, 'am_peak': 0.22, 'midday': 0.33, 'pm_peak': 0.24, 'evening': 0.12, 'owl': 0.04} | assumed weekday profile, **not COTA-observed** |

Cost weights (equivalent in-vehicle minutes) are in `config/cost_weights.yaml`.

## NEXT RESEARCH STEPS

1. Retrieve the NTD agency profile for COTA and reconcile scheduled vehicle-hours/miles against reported actuals; this is the single highest-value validation available without a records request.
2. Stand up sustained GTFS-Realtime collection to build empirical segment runtime distributions; this converts the reliability cost term from a placeholder into a measured quantity and reveals where schedule padding is mis-allocated.
3. File a public records request for stop-level and trip-level APC boardings; this replaces the LODES proxy with observed demand and is the precondition for claiming a real COTA optimization result.
4. Exploit GTFS `block_id` to reconstruct vehicle blocks, giving a true peak-vehicle count including interlining and layover rather than the continuous cycle/headway approximation.
5. Implement RAPTOR or CSA over the existing network abstraction so passenger cost is computed on actual OD paths rather than route-level aggregates; this is what makes transfer timing optimizable.
6. Add ACS zero-car-household and transit-commute variables as reporting dimensions (equity impact of any plan), kept strictly out of the objective function.

## EXPERIMENT 1 RESULT (summary)

See `outputs/experiments/` for the full record. Headline: a frequency redistribution inside the same scheduled vehicle-hour and peak-vehicle envelope, evaluated against the **LODES-derived proxy demand**, not observed ridership.
