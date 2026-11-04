# Modelled assumptions

FleetWave models a **synthetic** fleet on a regulated multi-service banking platform. None of
these numbers come from a real organisation. They are planning assumptions, chosen to be
plausible and then **calibrated so the modelled baseline reproduces the reported 60–90 day
upgrade cycle**. Replace them with measured values when real data is available.

Units: durations are **working days** (Mon–Fri, excluding England & Wales bank holidays).
Each duration is a three-point estimate (min / likely / max), sampled in Phase 3. Phases 1–2
use the *likely* value, and a task occupies `ceil(upgrade + test)` whole days (at least 1).

## Calendar and governance

| Item | Value | Justification |
|---|---|---|
| Cycle start | Mon 4 Jan 2027 | First full week after the usual festive change freeze lifts. |
| Bank holidays | 26 Mar, 29 Mar, 3 May, 31 May, 30 Aug 2027 | Published E&W bank holidays: no planned change or testing. |
| Prod weekdays | Tue, Wed, Thu | Avoid Mondays (weekend batch backlog, incidents) and Fridays (thin weekend cover). Common change-policy rule. |
| CAB | Weekly, Thursday | Typical weekly change-approval board. A prod change needs approval at a CAB held **after** pre-prod evidence exists and **before** the change, so it can start from the day after CAB. |
| Month-end freeze | Last 3 working days, prod only | Finance and regulatory reporting close. |
| Payday freeze | 1 working day either side of the 25th (rolled back to a working day), prod only | Salary credit peak, and BACS processing risk. |
| Peak freeze | 29 Mar–9 Apr 2027, pre-prod + prod | Tax-year end and ISA season: peak volumes, and business-testing use of pre-prod. |
| Horizon | 260 working days | Roomy enough that no schedule is cut off. |

## Capacity

| Item | Value | Justification |
|---|---|---|
| Parallel upgrades | 2 | Platform team of about 4–6 engineers, pairing on each upgrade for safety (two upgrades at once). Soak time and application-team remediation use none of this capacity. |
| Prod upgrades per week | ≤ 3 | Limits change risk and ops load per week. |
| Tier-1 prod per day | ≤ 1 | Never two critical services changing on the same day, so incidents stay attributable and recoverable. |
| Baseline streams | 2 | Today's process gets the **same** capacity as the optimiser, so any improvement comes from scheduling, not extra people. |

## Per-environment work (working days)

`upgrade` = control-plane and node-pool upgrade plus health checks. `test` = manual
regression and non-functional testing afterwards. Soak = observation before promoting.

| Tier | Env | upgrade min/likely/max | test min/likely/max | task days | soak |
|---|---|---|---|---|---|
| 1 | dev | 0.25 / 0.5 / 1 | 0.25 / 0.5 / 1 | 1 | 1 |
| 1 | test | 0.25 / 0.5 / 1 | 1 / 1.5 / 3 | 2 | 2 |
| 1 | preprod | 0.5 / 0.5 / 1 | 1 / 1.5 / 3 | 2 | 3 |
| 1 | prod | 0.25 / 0.5 / 1 | 0.25 / 0.5 / 1 | 1 | 2 |
| 2 | dev | 0.25 / 0.5 / 1 | 0.25 / 0.5 / 1 | 1 | 1 |
| 2 | test | 0.25 / 0.5 / 1 | 0.5 / 1 / 2 | 2 | 1 |
| 2 | preprod | 0.25 / 0.5 / 1 | 0.5 / 1 / 2 | 2 | 2 |
| 2 | prod | 0.25 / 0.5 / 1 | 0.25 / 0.5 / 1 | 1 | 1 |
| 3 | dev/test | 0.25 / 0.5 / 1 | 0.25 / 0.5 / 1 | 1 | 1 |
| 3 | preprod | 0.25 / 0.5 / 1 | 0.25 / 0.5 / 1.5 | 1 | 1 |
| 3 | prod | 0.25 / 0.5 / 1 | 0.25 / 0.5 / 1 | 1 | 1 |

Justification:

- An AKS control-plane plus node-pool upgrade takes hours, so half a day including checks is typical. The max covers drain problems.
- Testing dominates, and grows with criticality. Tier 1 needs fuller regression, plus performance testing in pre-prod.
- Soak grows towards prod and with tier. Prod soak is shorter because monitoring there is richest.
- The `max` values are roughly 2× likely: right-skewed, as overruns are more common than early finishes.

## Clusters, tiers and dependencies

| Cluster | Tier | Depends on | Latent blockers |
|---|---|---|---|
| identity | 1 | – | 2 |
| fraud-detection | 2 | – | 1 |
| payments | 1 | identity, fraud-detection | 3 |
| mobile-banking | 1 | identity | 2 |
| online-banking | 1 | identity | 1 |
| cards | 1 | identity, payments | 2 |
| savings | 2 | identity | 1 |
| mortgages | 2 | identity | 2 |
| lending | 3 | identity | 1 |
| data-platform | 3 | – | 3 |

- **Dependencies:** in each environment, a cluster upgrades only after the clusters it depends on have finished upgrading there. Identity is shared authentication; payments calls fraud scoring; cards calls payments. No extra soak is added for a dependency, because each cluster's own soak covers stability. (Adding dependency soak made the identity → payments → cards chain unrealistically long.)
- **Latent blockers:** issues present before the upgrade starts, such as removed APIs in Helm charts, blocking PodDisruptionBudgets or missing probes. They're higher where there are more teams or operators (payments, data-platform). From Phase 5 these come from the scanner, not this table.

## Late discovery and rework (today's process)

| Item | Value | Justification |
|---|---|---|
| Late-discovery probability | 0.5 | Without a pre-upgrade scan, about half the blockers only show up when a prod-like environment is upgraded. Pre-prod has prod-like configuration and scale (PDBs, replica counts, real charts), so it's where they surface. |
| Deterministic late count | `latent × 0.5`, rounded half up, per cluster | Expected value, used by the Phase 1 baseline (12 late blockers fleet-wide). Phase 3 samples it instead. |
| Fix time | 1 / 2 / 4 days per blocker | Diagnose, change the manifest or chart, review, redeploy. Done by **application teams**, so it adds elapsed time but uses no platform capacity. |
| Rework | Re-test in test env, then re-verify pre-prod | Both rerun the *test* effort only; the cluster is already on the new version. No extra soak, because the version already soaked and the fix is checked by the regression run. |

## Today's process (baseline policy)

The team works one environment wave at a time (all dev, then all test, then all pre-prod
including rework, then prod). Within a wave it picks up the next ready job, in dependency
order. Test and pre-prod waves wait until the previous wave has soaked everywhere. Prod
changes go to CAB cluster by cluster.

## Calibration notes (read before quoting numbers)

- With these assumptions the deterministic baseline is **79 calendar days** (57 working days), within the reported 60–90 range. Without late blockers it would be 59 days, so late discovery costs about 20 days.
- The result is **sensitive to the start date**. Starting one week later (11 Jan) gives 93 days, because the prod wave then runs into the late-March and April freezes: payday, month-end, Easter and the tax-year-end freeze. Freeze timing is a real driver of cycle length, and Phase 3 measures the risk.
- These are model outputs under stated assumptions, not measurements.
