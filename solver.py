import pulp as pl
from collections import defaultdict


def solve_food_survival_buckets_with_waste(
    buckets,
    people,
    calories_per_person,
    H=365,
    enforce_no_waste=True,
    solver_msg=False,
):
    """
    buckets: [{"name": str, "calories": float, "last_day": int|None}, ...]
    people:  number of people
    calories_per_person: daily caloric target per person
    H:       planning horizon in days
    """
    D = people * calories_per_person
    days = range(1, H + 1)
    B = range(len(buckets))

    m = pl.LpProblem("EmergencyFoodAllocation_Buckets", pl.LpMaximize)

    # x[b,t] = calories consumed from bucket b on day t
    x = pl.LpVariable.dicts("x", (B, days), lowBound=0)
    # y[t] = 1 if day t is survived
    y = pl.LpVariable.dicts("y", days, cat="Binary")

    # Objective: maximise days survived
    m += pl.lpSum(y[t] for t in days)

    # Daily caloric constraints
    for t in days:
        m += pl.lpSum(x[b][t] for b in B) >= D * y[t], f"daily_req_{t}"
        if enforce_no_waste:
            m += pl.lpSum(x[b][t] for b in B) <= D * y[t], f"no_waste_{t}"

    # Consecutive survival (can't skip a day)
    for t in range(1, H):
        m += y[t] >= y[t + 1], f"consecutive_{t}"

    # Inventory and expiry
    for b in B:
        Qb = float(buckets[b]["calories"])
        Lb = buckets[b]["last_day"]
        m += pl.lpSum(x[b][t] for t in days) <= Qb, f"inventory_{b}"
        if Lb is not None:
            Lb = int(Lb)
            for t in days:
                if t > Lb:
                    m += x[b][t] == 0, f"expiry_b{b}_d{t}"

    solver = pl.PULP_CBC_CMD(msg=solver_msg)
    status = m.solve(solver)
    status_str = pl.LpStatus[status]

    if status_str not in ("Optimal", "Feasible"):
        return {
            "status": status_str,
            "max_days": 0,
            "schedule": [],
            "waste_by_day": [],
            "total_waste_by_bucket": {},
        }

    max_days = int(round(sum(pl.value(y[t]) for t in days)))

    # Build consumption schedule
    schedule = []
    consumed_by_bucket = {b: 0.0 for b in B}
    consumed_cum = {b: {} for b in B}

    for t in days:
        row = {"day": t, "survived": int(round(pl.value(y[t])))}
        total = 0.0
        for b in B:
            val = max(0.0, float(pl.value(x[b][t])))
            row[buckets[b]["name"]] = val
            total += val
            consumed_by_bucket[b] += val
            consumed_cum[b][t] = consumed_by_bucket[b]
        row["total"] = total
        schedule.append(row)

    # Waste calculation (crystallised at expiry day)
    waste_day_totals = defaultdict(float)
    waste_day_breakdown = defaultdict(dict)
    total_waste_by_bucket = {}

    for b in B:
        name = buckets[b]["name"]
        Qb = float(buckets[b]["calories"])
        Lb = buckets[b]["last_day"]
        if Lb is None:
            total_waste_by_bucket[name] = 0.0
            continue
        Lb = int(Lb)
        consumed_through_L = consumed_cum[b].get(Lb, 0.0)
        waste = max(0.0, Qb - consumed_through_L)
        total_waste_by_bucket[name] = waste
        if waste > 0:
            waste_day_totals[Lb] += waste
            waste_day_breakdown[Lb][name] = waste

    waste_by_day = []
    for t in days:
        waste_row = {"day": t, "waste_total": float(waste_day_totals.get(t, 0.0))}
        for name, w in waste_day_breakdown.get(t, {}).items():
            waste_row[name] = float(w)
        waste_by_day.append(waste_row)

    return {
        "status": status_str,
        "max_days": max_days,
        "schedule": schedule,
        "waste_by_day": waste_by_day,
        "total_waste_by_bucket": total_waste_by_bucket,
    }


def compute_expiry_alerts(result, buckets, people, calories_per_person_full):
    """
    Returns dict keyed by day -> list of alert dicts.
    Alerts appear on the expiry day and the day before.
    Extra rations always relative to FULL ration.
    """
    full_daily = people * calories_per_person_full
    alerts = {}

    for b, bucket in enumerate(buckets):
        if bucket["last_day"] is None:
            continue
        L = int(bucket["last_day"])

        scheduled_through_L = sum(
            row.get(bucket["name"], 0.0)
            for row in result["schedule"]
            if row["day"] <= L
        )
        extra_calories = max(0.0, bucket["calories"] - scheduled_through_L)
        if extra_calories < 1.0:
            continue

        extra_full_rations = extra_calories / full_daily
        alert = {
            "bucket": bucket["name"],
            "expires_day": L,
            "extra_calories": extra_calories,
            "extra_full_rations": extra_full_rations,
        }
        alerts.setdefault(L, []).append({**alert, "type": "expiry"})
        if L > 1:
            alerts.setdefault(L - 1, []).append({**alert, "type": "warning"})

    return alerts
