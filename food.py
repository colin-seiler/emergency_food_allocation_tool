import pulp as pl
from collections import defaultdict

def solve_food_survival_buckets_with_waste(
    buckets,                   # [{"name":..., "calories":..., "last_day": int|None}, ...]
    people,
    calories_per_person,
    H=365,
    enforce_no_waste=True,     # if True, no consumption on days you don't survive
    solver_msg=False
):
    D = people * calories_per_person
    days = range(1, H + 1)
    B = range(len(buckets))

    m = pl.LpProblem("EmergencyFoodAllocation_Buckets", pl.LpMaximize)

    # x[b,t] calories consumed from bucket b on day t
    x = pl.LpVariable.dicts("x", (B, days), lowBound=0)

    # y[t] = 1 if day t is survived
    y = pl.LpVariable.dicts("y", days, cat="Binary")

    # Objective
    m += pl.lpSum(y[t] for t in days)

    # Daily constraints
    for t in days:
        m += pl.lpSum(x[b][t] for b in B) >= D * y[t], f"daily_requirement_{t}"
        if enforce_no_waste:
            m += pl.lpSum(x[b][t] for b in B) <= D * y[t], f"no_waste_{t}"

    # Consecutive days
    for t in range(1, H):
        m += y[t] >= y[t+1], f"consecutive_{t}"

    # Inventory + expiration cutoffs
    for b in B:
        Qb = float(buckets[b]["calories"])
        Lb = buckets[b]["last_day"]

        m += pl.lpSum(x[b][t] for t in days) <= Qb, f"inventory_{b}"

        if Lb is not None:
            Lb = int(Lb)
            for t in days:
                if t > Lb:
                    m += x[b][t] == 0, f"expiry_bucket{b}_day{t}"

    # Solve
    solver = pl.PULP_CBC_CMD(msg=solver_msg)
    status = m.solve(solver)
    status_str = pl.LpStatus[status]
    if status_str not in ("Optimal", "Feasible"):
        return {"status": status_str, "max_days": 0, "schedule": [], "waste_by_day": [], "total_waste_by_bucket": {}}

    max_days = int(round(sum(pl.value(y[t]) for t in days)))

    # Build consumption schedule
    schedule = []
    consumed_by_bucket = {b: 0.0 for b in B}
    consumed_cum_by_day_bucket = {b: {} for b in B}

    for t in days:
        row = {"day": t, "survived": int(round(pl.value(y[t])))}
        total = 0.0
        for b in B:
            val = float(pl.value(x[b][t]))
            row[buckets[b]["name"]] = val
            total += val

            consumed_by_bucket[b] += val
            consumed_cum_by_day_bucket[b][t] = consumed_by_bucket[b]
        row["total"] = total
        schedule.append(row)

    # Waste calculation:
    # For each expiring bucket with last_day=L,
    # waste_on_day_L = Qb - (consumed up through day L)
    waste_by_day = []
    waste_day_totals = defaultdict(float)
    waste_day_bucket_breakdown = defaultdict(dict)
    total_waste_by_bucket = {}

    for b in B:
        name = buckets[b]["name"]
        Qb = float(buckets[b]["calories"])
        Lb = buckets[b]["last_day"]

        if Lb is None:
            total_waste_by_bucket[name] = 0.0
            continue

        Lb = int(Lb)
        consumed_through_L = consumed_cum_by_day_bucket[b].get(Lb, 0.0)
        waste = max(0.0, Qb - consumed_through_L)

        total_waste_by_bucket[name] = waste
        waste_day_totals[Lb] += waste
        waste_day_bucket_breakdown[Lb][name] = waste

    for t in days:
        waste_row = {"day": t, "waste_total": float(waste_day_totals.get(t, 0.0))}
        # include breakdown only where waste occurs (optional; here we include keys if present)
        for name, w in waste_day_bucket_breakdown.get(t, {}).items():
            waste_row[name] = float(w)
        waste_by_day.append(waste_row)

    return {
        "status": status_str,
        "max_days": max_days,
        "schedule": schedule,
        "waste_by_day": waste_by_day,
        "total_waste_by_bucket": total_waste_by_bucket
    }
