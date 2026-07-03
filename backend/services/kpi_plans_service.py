from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from db import get_db, q, _use_pg


WEIGHTS: dict[str, int] = {
    "visits": 8,  # выездная экспертиза
    "messenger": 3,  # мессенджер/сделка (заглушка: кол-во принятых КП)
    "leads": 2,  # лид/регистрация
    "calls": 1,  # звонок
}

DAY_CAP_UNITS: int = 10  # дневная ёмкость (ед.)


def _parse_day_str(d: Any) -> Optional[date]:
    """
    Accept:
      - 'YYYY-MM-DD' strings
      - 'YYYY-MM-DDTHH:MM...' strings
      - date/datetime
    """
    if d is None:
        return None
    if isinstance(d, date) and not isinstance(d, datetime):
        return d
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, str):
        if len(d) >= 10:
            try:
                return datetime.fromisoformat(d[:19].replace("Z", "+00:00")).date()
            except Exception:
                try:
                    return datetime.strptime(d[:10], "%Y-%m-%d").date()
                except Exception:
                    return None
    return None


def _month_bounds(year: int, month: int) -> Tuple[datetime, datetime]:
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
    return start, end


def _get_work_days(year: int, month: int) -> List[date]:
    # Mon-Fri only (no Sat=5, Sun=6)
    start, end = _month_bounds(year, month)
    cur = start.date()
    last = (end - timedelta(days=1)).date()
    out: List[date] = []
    while cur <= last:
        if cur.weekday() < 5:
            out.append(cur)
        cur = cur + timedelta(days=1)
    return out


def _today_in_month(work_days: List[date], now: date) -> int:
    # returns passedDays count (>=0 <= len(work_days))
    if not work_days:
        return 0
    first = work_days[0]
    last = work_days[-1]
    if now < first:
        return 0
    if now > last:
        return len(work_days)
    passed = 0
    for d in work_days:
        if d <= now:
            passed += 1
    return passed


@dataclass(frozen=True)
class DailyCounts:
    visits: int = 0
    messenger: int = 0
    leads: int = 0
    calls: int = 0

    @property
    def used_units(self) -> int:
        return (
            self.visits * WEIGHTS["visits"]
            + self.messenger * WEIGHTS["messenger"]
            + self.leads * WEIGHTS["leads"]
            + self.calls * WEIGHTS["calls"]
        )


def _compute_adjusted_plan_units(base_plan_units: int, work_days: List[date], daily: Dict[date, DailyCounts]) -> int:
    passed_days = 0
    now = date.today()
    # adjust based on days with trips so far (current view)
    for d in work_days:
        if d <= now:
            passed_days += 1
    days_with_trips = 0
    for d in work_days:
        if d <= now:
            if daily.get(d, DailyCounts()).visits > 0:
                days_with_trips += 1

    total_work_days = len(work_days)
    if total_work_days <= 0:
        return 0
    # matches ТЗ: base * (work_days - days_with_trips)/work_days
    adjusted = base_plan_units * (total_work_days - days_with_trips) / total_work_days
    adjusted_units = int(round(adjusted))
    return max(0, adjusted_units)


def _build_lines(work_days: List[date], passed_days: int, daily: Dict[date, DailyCounts], adjusted_plan_units: int) -> Tuple[List[Optional[int]], List[int]]:
    """
    Returns:
      fact_cum: length=work_days, numbers for i<passed_days and have day counts; else null
      plan_cum: length=work_days, always filled based on adjusted_plan_units
    """
    fact_cum: List[Optional[int]] = []
    fact_total = 0

    total = len(work_days)
    daily_plan = (adjusted_plan_units / total) if total > 0 else 0

    for i, d in enumerate(work_days):
        if i < passed_days:
            counts = daily.get(d, DailyCounts())
            fact_total += counts.used_units
            fact_cum.append(int(round(fact_total)))
        else:
            fact_cum.append(None)

    plan_cum: List[int] = []
    for i in range(total):
        plan_cum.append(int(round(daily_plan * (i + 1))))
    return fact_cum, plan_cum


def _capacity_pct(used_units: int) -> int:
    if DAY_CAP_UNITS <= 0:
        return 0
    return int(round(min(1.0, used_units / DAY_CAP_UNITS) * 100))


def _fetch_user_plans(conn: Any, year: int, month: int) -> List[Dict[str, Any]]:
    cur = conn.cursor()
    # Use employee plans rows for month/year
    cur.execute(
        q(
            """
            SELECT ep.user_id, u.name as user_name, ep.calls_target, ep.registrations_target
            FROM employee_plans ep
            JOIN users u ON u.id = ep.user_id
            WHERE ep.month = %s AND ep.year = %s AND u.role IN ('employee','manager')
            ORDER BY u.name
            """
        ),
        (month, year),
    )
    rows = cur.fetchall()
    return [
        {
            "user_id": r[0],
            "user_name": r[1],
            "calls_target": int(r[2] or 0),
            "registrations_target": int(r[3] or 0),
        }
        for r in rows
    ]


def _fetch_daily_counts(
    conn: Any,
    user_ids: List[int],
    year: int,
    month: int,
) -> Dict[int, Dict[date, DailyCounts]]:
    start_dt, end_dt = _month_bounds(year, month)
    start_str = start_dt.isoformat()
    end_str = end_dt.isoformat()

    out: Dict[int, Dict[date, DailyCounts]] = {uid: {} for uid in user_ids}
    if not user_ids:
        return out

    placeholders = ",".join(["%s"] * len(user_ids)) if _use_pg else ",".join(["?"] * len(user_ids))

    cur = conn.cursor()

    # Trips (выездная экспертиза): calendar_events.kind='meeting'
    cur.execute(
        f"""
        SELECT user_id, start, COALESCE(kind,'') as kind
        FROM calendar_events
        WHERE user_id IN ({placeholders})
          AND kind = 'meeting'
          AND start >= %s AND start < %s
        """,
        (*user_ids, start_str, end_str),
    )
    for user_id, start_val, _kind in cur.fetchall():
        d = _parse_day_str(start_val)
        if not d:
            continue
        cur_day = out[user_id].get(d, DailyCounts())
        out[user_id][d] = DailyCounts(
            visits=cur_day.visits + 1,
            messenger=cur_day.messenger,
            leads=cur_day.leads,
            calls=cur_day.calls,
        )

    # Leads + Calls from call_logs
    cur.execute(
        f"""
        SELECT user_id, call_date, status, is_new_registration
        FROM call_logs
        WHERE user_id IN ({placeholders})
          AND call_date >= %s AND call_date < %s
        """,
        (*user_ids, start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")),
    )
    for user_id, call_date_val, status_val, is_new_reg in cur.fetchall():
        d = _parse_day_str(call_date_val)
        if not d:
            continue
        cur_day = out[user_id].get(d, DailyCounts())
        new_calls = cur_day.calls + (1 if status_val == "completed" else 0)
        new_leads = cur_day.leads + (1 if bool(is_new_reg) else 0)
        out[user_id][d] = DailyCounts(
            visits=cur_day.visits,
            messenger=cur_day.messenger,
            leads=new_leads,
            calls=new_calls,
        )

    # Messenger/deals: accepted KP proposals
    # Deal count = number of proposals accepted (status='accepted') by client click
    cur.execute(
        f"""
        SELECT created_by, accepted_at
        FROM proposals
        WHERE created_by IN ({placeholders})
          AND status = 'accepted'
          AND accepted_at IS NOT NULL
          AND accepted_at >= %s AND accepted_at < %s
        """,
        (*user_ids, start_str, end_str),
    )
    for user_id, accepted_at_val in cur.fetchall():
        d = _parse_day_str(accepted_at_val)
        if not d:
            continue
        cur_day = out[user_id].get(d, DailyCounts())
        out[user_id][d] = DailyCounts(
            visits=cur_day.visits,
            messenger=cur_day.messenger + 1,
            leads=cur_day.leads,
            calls=cur_day.calls,
        )

    return out


def build_kpi_payload(
    *,
    current_user: Dict[str, Any],
    year: int,
    month: int,
) -> Dict[str, Any]:
    conn = get_db()
    try:
        plans = _fetch_user_plans(conn, year=year, month=month)

        if current_user["role"] in ("admin", "manager"):
            managers = plans
        else:
            managers = [p for p in plans if p["user_id"] == current_user["id"]]

        user_ids = [m["user_id"] for m in managers]
        daily_counts_by_user = _fetch_daily_counts(conn, user_ids=user_ids, year=year, month=month)

        work_days = _get_work_days(year, month)
        now_day = date.today()
        passed_days = _today_in_month(work_days, now_day)

        payload_managers: List[Dict[str, Any]] = []
        for m in managers:
            uid = m["user_id"]
            daily_counts = daily_counts_by_user.get(uid, {})
            base_plan_units = int(m["calls_target"] or 0)
            adjusted_plan_units = _compute_adjusted_plan_units(base_plan_units, work_days, daily_counts)

            fact_cum, plan_cum = _build_lines(work_days, passed_days, daily_counts, adjusted_plan_units)

            # Today stats
            today_used = daily_counts.get(now_day, DailyCounts()).used_units if now_day in daily_counts else DailyCounts().used_units
            cap_today_pct = _capacity_pct(today_used)

            # Monthly totals (so far? or all month). For cards use totals by month so far (по факту) up to today.
            month_totals = DailyCounts()
            for d in work_days:
                if d <= now_day:
                    cd = daily_counts.get(d, DailyCounts())
                    month_totals = DailyCounts(
                        visits=month_totals.visits + cd.visits,
                        messenger=month_totals.messenger + cd.messenger,
                        leads=month_totals.leads + cd.leads,
                        calls=month_totals.calls + cd.calls,
                    )

            last_fact = 0
            for v in reversed(fact_cum):
                if v is not None:
                    last_fact = v
                    break
            plan_at_today = plan_cum[passed_days - 1] if passed_days > 0 else 0
            completion_pct = int(round((last_fact / adjusted_plan_units) * 100)) if adjusted_plan_units > 0 else 0

            daily_details = []
            for i, d in enumerate(work_days):
                cd = daily_counts.get(d, DailyCounts())
                daily_details.append(
                    {
                        "date": d.isoformat(),
                        "visits": cd.visits,
                        "messenger": cd.messenger,
                        "leads": cd.leads,
                        "calls": cd.calls,
                        "used_units": cd.used_units,
                        "capacity_pct": _capacity_pct(cd.used_units),
                        "is_past": i < passed_days,
                    }
                )

            payload_managers.append(
                {
                    "user_id": uid,
                    "user_name": m["user_name"],
                    "base_plan_units": base_plan_units,
                    "adjusted_plan_units": adjusted_plan_units,
                    "work_days": [d.isoformat() for d in work_days],
                    "passed_days": passed_days,
                    "fact_cum": fact_cum,
                    "plan_cum": plan_cum,
                    "daily_details": daily_details,
                    "stats": {
                        "completion_pct": completion_pct,
                        "cap_today_pct": cap_today_pct,
                        "leads_month_total": month_totals.leads,
                        "visits_month_total": month_totals.visits,
                        "calls_month_total": month_totals.calls,
                        "messenger_month_total": month_totals.messenger,
                        "delta_units": last_fact - plan_at_today,
                    },
                }
            )

        return {
            "year": year,
            "month": month,
            "work_days_count": len(work_days),
            "managers": payload_managers,
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass
