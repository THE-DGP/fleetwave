"""Plotly charts: Gantt chart of a schedule with freeze windows shaded."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from fleetwave.models import Env, FleetConfig, Schedule, TaskKind
from fleetwave.scheduler.calendar import WorkCalendar

COLOURS: dict[str, str] = {
    "dev": "#7fb3d5",
    "test": "#5499c7",
    "preprod": "#2471a3",
    "prod": "#1b2631",
    "remediation": "#e67e22",
    "rework": "#c0392b",
}


def schedule_frame(schedule: Schedule, fleet: FleetConfig, cal: WorkCalendar) -> pd.DataFrame:
    """One row per task with real dates (finish is exclusive, for plotting)."""
    rows = []
    for t in schedule.tasks:
        rows.append(
            {
                "cluster": t.cluster,
                "tier": fleet.cluster(t.cluster).tier,
                "env": t.env.value,
                "kind": t.kind.value,
                "category": t.env.value if t.kind is TaskKind.UPGRADE else t.kind.value,
                "start_day": t.start,
                "end_day": t.end,
                "start": cal.date(t.start),
                "finish": cal.date(t.end - 1) + dt.timedelta(days=1),
                "note": t.note,
            }
        )
    return pd.DataFrame(rows)


def gantt(schedule: Schedule, fleet: FleetConfig, cal: WorkCalendar, title: str = "") -> go.Figure:
    """Gantt chart: one row per cluster, coloured by environment / rework, prod freezes shaded."""
    df = schedule_frame(schedule, fleet, cal)
    fig = px.timeline(
        df,
        x_start="start",
        x_end="finish",
        y="cluster",
        color="category",
        color_discrete_map=COLOURS,
        hover_data=["env", "kind", "note", "start_day", "end_day"],
        category_orders={
            "cluster": fleet.topological_order(),
            "category": list(COLOURS),
        },
    )
    finish = schedule.finish_date + dt.timedelta(days=1)
    x_max = finish + dt.timedelta(days=10)
    for first, last, reason in cal.freeze_ranges(Env.PROD):
        if first > x_max:
            break
        fig.add_vrect(
            x0=first,
            x1=last + dt.timedelta(days=1),
            fillcolor="#f5b7b1",
            opacity=0.35,
            line_width=0,
            layer="below",
            name=reason,
        )
    fig.add_vline(x=finish, line_dash="dash", line_color="black")
    fig.update_xaxes(range=[schedule.start_date - dt.timedelta(days=3), x_max])
    fig.update_layout(
        title=title
        or (
            f"{schedule.method}: {schedule.makespan_calendar_days} calendar days "
            f"({schedule.start_date} to {schedule.finish_date})"
        ),
        xaxis_title="date (shaded = prod change freeze)",
        yaxis_title="",
        legend_title="work",
        height=520,
    )
    return fig
