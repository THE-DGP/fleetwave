# Azure Boards backlog

Import `docs/backlog.csv` (see docs/setup.md, step 6). If the import fails, create these by hand.
Hierarchy (Agile process): **Epic > Feature > User Story**. There is one Epic per layer, plus a
cross-cutting Delivery Epic for Phases 0 and 5, which belong to neither layer.

## Epic: Layer 3 - Upgrade Wave Scheduler

Find the fastest safe upgrade schedule for a 10-cluster, 4-environment fleet under CAB, freeze, maintenance-window and capacity constraints, and quantify completion risk.

### Feature: Phase 1 - Fleet data model and baseline

- **User Story: Define fleet and constraints as validated config**
  - As a platform engineer I can describe clusters, tiers, environments, durations, soak times, dependencies and calendar rules in config/fleet.yaml, validated by pydantic models.
  - *Acceptance criteria:* fleet.yaml has 10 clusters x 4 envs; invalid config (min>max, unknown dependency, cycle) is rejected with a clear error; tests cover each validation.
- **User Story: Simulate the current sequential upgrade process**
  - As a platform lead I can see how long today's one-cluster-at-a-time manual process takes, including late-blocker rework.
  - *Acceptance criteria:* baseline.py respects freezes, CAB and prod weekdays; baseline makespan lands between 60 and 90 days; result is reproducible with a fixed seed.
- **User Story: Visualise schedules and document assumptions**
  - As a stakeholder I can view any schedule as a Gantt chart and see where every modelled number came from.
  - *Acceptance criteria:* Plotly Gantt HTML written to reports/; docs/assumptions.md justifies every duration and probability.

### Feature: Phase 2 - CP-SAT optimiser

- **User Story: Model upgrade tasks as CP-SAT interval variables**
  - As a planner I get one interval per (cluster, environment) plus optional remediation tasks, with environment order, soak gaps and cluster dependencies enforced.
  - *Acceptance criteria:* Unit tests prove env order, soak gap and cross-cluster dependency are never violated.
- **User Story: Enforce calendar and capacity constraints**
  - As a change manager I am guaranteed the schedule respects freezes, Tue-Thu prod days, prior-CAB approval, max 3 prod per week, max 2 parallel upgrades and no two tier-1 prod upgrades on one day.
  - *Acceptance criteria:* One passing unit test per constraint (e.g. no prod task inside any freeze).
- **User Story: Optimise makespan and report solver status**
  - As a planner I get the shortest schedule, with tier-1 prod changes spread apart, within a time limit.
  - *Acceptance criteria:* Solver is time-limited; status OPTIMAL/FEASIBLE is reported; choice of weighted vs two-stage objective is documented.

### Feature: Phase 3 - Monte Carlo and scenarios

- **User Story: Simulate completion risk**
  - As a platform lead I see P50/P80/P95 completion dates rather than a single optimistic date.
  - *Acceptance criteria:* 1,000+ runs per scenario using PERT/triangular durations, late-rework probability and random approval delays; runtime documented.
- **User Story: Compare scenarios A-D**
  - As a decision maker I can compare baseline, optimised waves, shift-left readiness and automated testing.
  - *Acceptance criteria:* Comparison table, histogram overlay and per-scenario Gantt produced from real runs and written to docs/results.md.

## Epic: Layer 1 - Readiness Scanner

Find upgrade blockers in each cluster before the upgrade starts and score each cluster's readiness 0-100.

### Feature: Phase 4 - kind lab with planted issues

- **User Story: Build a local multi-cluster lab**
  - As a developer I can create 3-4 kind clusters on an older Kubernetes version and deploy sample banking apps with Helm.
  - *Acceptance criteria:* Scripts create/destroy the lab; charts plant removed APIs, blocking PDBs, single replicas, missing probes and missing requests; one cluster is clean.

### Feature: Phase 4 - Checks, scoring and reports

- **User Story: Scan live clusters and offline manifests**
  - As a CI pipeline I can scan a directory of rendered manifests with no cluster; as an engineer I can scan a live cluster.
  - *Acceptance criteria:* Offline and live modes produce the same findings for the same workloads.
- **User Story: Implement readiness checks**
  - As a platform engineer I am told about removed/deprecated APIs, blocking PDBs, single points of failure, missing probes, missing requests and version skew.
  - *Acceptance criteria:* Each check has unit tests; 100% of planted issues flagged and zero findings on the healthy cluster.
- **User Story: Score clusters and report findings**
  - As a service owner I see a 0-100 score, RAG status and actionable findings for my cluster.
  - *Acceptance criteria:* JSON and Markdown reports; each finding has severity, resource, why it blocks the upgrade and the fix.

## Epic: Delivery - Setup, Integration and CI

Cross-cutting work: tooling, Azure DevOps setup, linking the two layers, dashboard, pipeline and write-up.

### Feature: Phase 0 - Project setup

- **User Story: Create repo skeleton and tooling**
  - As a developer I have a Python 3.11+ package with ruff, pytest and coverage configured.
  - *Acceptance criteria:* ruff check passes; pytest runs; repo pushed to GitHub and Azure Repos.
- **User Story: Set up Azure DevOps**
  - As the project owner I have an Azure DevOps project with Repos, this Boards backlog and pipeline capacity.
  - *Acceptance criteria:* Backlog imported; parallel-job grant requested or self-hosted agent registered; Phase 0 pipeline run is green.

### Feature: Phase 5 - Integration, dashboard, CI and write-up

- **User Story: Feed scanner findings into the scheduler**
  - As a planner each blocker becomes a remediation task with a severity-based duration.
  - *Acceptance criteria:* fleetwave run --config config/fleet.yaml --manifests ./scan-input runs scan, schedule and simulate end to end.
- **User Story: Build the Streamlit dashboard**
  - As a stakeholder I can explore readiness, the optimised schedule, risk and scenario comparison.
  - *Acceptance criteria:* Four pages: Fleet Readiness, Optimised Schedule, Risk, Scenario Comparison.
- **User Story: Automate in Azure Pipelines with a readiness gate**
  - As a release manager the pipeline lints, tests, scans, schedules and publishes reports, and fails if any cluster is below the threshold.
  - *Acceptance criteria:* Stages Lint, Test, Scan, Schedule & Simulate, Publish; threshold configurable; reports published as artifacts.
- **User Story: Write up the project**
  - As a job applicant I can explain the project clearly to recruiters and interviewers.
  - *Acceptance criteria:* README with diagram, quickstart, screenshots, results, assumptions, limitations and AKS mapping; 3-minute demo script; LinkedIn post.
