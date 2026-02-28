import streamlit as st
import pandas as pd
from solver import solve_food_survival_buckets_with_waste, compute_expiry_alerts

# ─────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Emergency Food Rationing",
    page_icon="🥫",
    layout="wide",
)

# ─────────────────────────────────────────────
# Minimal custom styling
# ─────────────────────────────────────────────
st.markdown(
    """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap');

        html, body, [class*="css"] {
            font-family: 'IBM Plex Sans', sans-serif;
        }
        h1, h2, h3 {
            font-family: 'IBM Plex Mono', monospace;
        }
        .ration-badge {
            font-family: 'IBM Plex Mono', monospace;
            font-size: 0.75rem;
            padding: 2px 8px;
            border-radius: 3px;
            background: #1e3a2f;
            color: #5aff9a;
            letter-spacing: 0.05em;
        }
        .stat-box {
            background: #0e1a14;
            border: 1px solid #2a4a38;
            border-radius: 6px;
            padding: 1rem 1.25rem;
            margin-bottom: 0.5rem;
        }
        .stat-box .label {
            font-family: 'IBM Plex Mono', monospace;
            font-size: 0.7rem;
            color: #5aff9a;
            letter-spacing: 0.1em;
            text-transform: uppercase;
        }
        .stat-box .value {
            font-family: 'IBM Plex Mono', monospace;
            font-size: 2rem;
            font-weight: 600;
            color: #e8f5ee;
        }
        .stDataFrame { border: 1px solid #2a4a38; }
        div[data-testid="stExpander"] {
            border: 1px solid #2a4a38;
            border-radius: 6px;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────
# Session state defaults
# ─────────────────────────────────────────────
DEFAULTS = {
    "food_items": [],
    "people": 50,
    "calories_per_person": 2000,
    "horizon": 60,
    "results": None,
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

RATION_SCENARIOS = {
    "Full (100%)": 1.0,
    "7/8 Ration":  7 / 8,
    "3/4 Ration":  3 / 4,
    "1/2 Ration":  1 / 2,
}

# ─────────────────────────────────────────────
# Sidebar — global parameters
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Parameters")
    st.session_state.people = st.number_input(
        "Number of people", min_value=1, value=st.session_state.people, step=1
    )
    st.session_state.calories_per_person = st.number_input(
        "Calories / person / day",
        min_value=500,
        value=int(st.session_state.calories_per_person),
        step=100,
    )
    st.session_state.horizon = st.number_input(
        "Planning horizon (days)",
        min_value=1,
        max_value=365,
        value=int(st.session_state.horizon),
        step=1,
    )

    st.divider()
    st.markdown(
        "<small>Full daily draw = "
        f"**{st.session_state.people * st.session_state.calories_per_person:,} cal**"
        "</small>",
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────
st.markdown("# 🥫 Emergency Food Rationing")
st.markdown(
    "Add your food inventory below. The solver will compute the maximum days "
    "your group can survive across multiple ration levels."
)
st.divider()

# ─────────────────────────────────────────────
# Food Inventory — input form
# ─────────────────────────────────────────────
st.markdown("## 1 · Food Inventory")

with st.form("add_food", clear_on_submit=True):
    c1, c2, c3, c4, c5 = st.columns([2, 1.5, 1.5, 1.5, 1])
    name          = c1.text_input("Food / bucket name", placeholder="e.g. Canned Beans")
    cal_per_unit  = c2.number_input("Calories per unit", min_value=1, value=200, step=10)
    units         = c3.number_input("Units (cans / items)", min_value=1, value=100, step=1)
    expiry_days   = c4.number_input(
        "Expires in N days (0 = never)", min_value=0, value=0, step=1
    )
    submitted = c5.form_submit_button("➕ Add", use_container_width=True)

    if submitted:
        if not name.strip():
            st.warning("Please enter a food name.")
        else:
            st.session_state.food_items.append(
                {
                    "name":     name.strip(),
                    "calories": int(cal_per_unit) * int(units),
                    "last_day": int(expiry_days) if expiry_days > 0 else None,
                    # keep originals for display
                    "_cal_per_unit": int(cal_per_unit),
                    "_units":        int(units),
                    "_expiry_days":  int(expiry_days) if expiry_days > 0 else None,
                }
            )
            st.session_state.results = None  # invalidate cached results

# ─── Current inventory table ───
if st.session_state.food_items:
    display_rows = []
    for i, item in enumerate(st.session_state.food_items):
        display_rows.append(
            {
                "#":              i + 1,
                "Name":           item["name"],
                "Cal / unit":     f"{item['_cal_per_unit']:,}",
                "Units":          item["_units"],
                "Total cal":      f"{item['calories']:,}",
                "Expires (day)":  item["_expiry_days"] if item["_expiry_days"] else "Never",
            }
        )
    df_display = pd.DataFrame(display_rows).set_index("#")
    st.dataframe(df_display, use_container_width=True)

    col_del, col_clear, _ = st.columns([1, 1, 4])
    with col_del:
        del_idx = st.number_input(
            "Delete row #", min_value=1,
            max_value=len(st.session_state.food_items),
            step=1, label_visibility="collapsed"
        )
    with col_clear:
        if st.button("🗑 Delete row"):
            st.session_state.food_items.pop(int(del_idx) - 1)
            st.session_state.results = None
            st.rerun()
    if st.button("🧹 Clear all inventory"):
        st.session_state.food_items = []
        st.session_state.results = None
        st.rerun()
else:
    st.info("No food items added yet. Use the form above to add inventory.")

st.divider()

# ─────────────────────────────────────────────
# Run optimisation
# ─────────────────────────────────────────────
st.markdown("## 2 · Optimise")

run_disabled = len(st.session_state.food_items) == 0

if st.button("▶ Run Optimisation", disabled=run_disabled, type="primary"):
    with st.spinner("Solving across ration scenarios…"):
        all_results = {}
        for label, factor in RATION_SCENARIOS.items():
            all_results[label] = solve_food_survival_buckets_with_waste(
                buckets=st.session_state.food_items,
                people=st.session_state.people,
                calories_per_person=st.session_state.calories_per_person * factor,
                H=int(st.session_state.horizon),
                enforce_no_waste=True,
                solver_msg=False,
            )
        st.session_state.results = all_results

if run_disabled:
    st.caption("Add at least one food item to run the optimiser.")

# ─────────────────────────────────────────────
# Results
# ─────────────────────────────────────────────
if st.session_state.results:
    st.divider()
    st.markdown("## 3 · Results")

    # ── Summary bar across all ration levels ──
    summary_cols = st.columns(len(RATION_SCENARIOS))
    for col, (label, factor) in zip(summary_cols, RATION_SCENARIOS.items()):
        res = st.session_state.results[label]
        with col:
            st.markdown(
                f"""
                <div class="stat-box">
                    <div class="label">{label}</div>
                    <div class="value">{res['max_days']}</div>
                    <div style="color:#7a9e8a;font-size:0.8rem">days survived</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.divider()

    # ── Per-ration tabs ──
    tabs = st.tabs(list(RATION_SCENARIOS.keys()))

    for tab, (label, factor) in zip(tabs, RATION_SCENARIOS.items()):
        res    = st.session_state.results[label]
        alerts = compute_expiry_alerts(
            result=res,
            buckets=st.session_state.food_items,
            people=st.session_state.people,
            calories_per_person_full=st.session_state.calories_per_person,
        )

        with tab:
            if res["max_days"] == 0:
                st.error(f"Solver status: {res['status']} — no feasible solution found.")
                continue

            cal_day = st.session_state.people * st.session_state.calories_per_person * factor
            st.markdown(
                f"Daily draw at this ration: **{cal_day:,.0f} cal** "
                f"({st.session_state.people} people × "
                f"{st.session_state.calories_per_person * factor:,.0f} cal/person)"
            )

            # ── Daily schedule ──
            st.markdown("### Daily Schedule")

            survived_schedule = [
                row for row in res["schedule"] if row["survived"] == 1
            ]

            for row in survived_schedule:
                day = row["day"]

                # Day header
                st.markdown(f"**Day {day}**")

                # Expiry alerts for this day
                if day in alerts:
                    for alert in alerts[day]:
                        bucket_name  = alert["bucket"]
                        extra_cal    = alert["extra_calories"]
                        extra_ration = alert["extra_full_rations"]

                        if alert["type"] == "expiry":
                            st.warning(
                                f"⚠️ **{bucket_name}** expires today — "
                                f"{extra_cal:,.0f} unscheduled calories available. "
                                f"Your group can consume **{extra_ration:.1f} extra full rations** "
                                f"before this food is lost."
                            )
                        else:
                            expires_day = alert["expires_day"]
                            st.info(
                                f"ℹ️ **{bucket_name}** expires on day {expires_day} (tomorrow). "
                                f"{extra_cal:,.0f} calories at risk — consider consuming "
                                f"**{extra_ration:.1f} extra full rations** today."
                            )

                # Row dict (raw for now, charts later)
                st.write(row)

            # ── Waste summary ──
            st.markdown("### Waste Summary")

            total_waste = res["total_waste_by_bucket"]
            any_waste   = any(v > 0 for v in total_waste.values())

            if not any_waste:
                st.success("✅ No food wasted under this ration scenario.")
            else:
                waste_rows = [
                    {"Bucket": k, "Calories wasted": f"{v:,.0f}"}
                    for k, v in total_waste.items()
                    if v > 0
                ]
                st.dataframe(
                    pd.DataFrame(waste_rows).set_index("Bucket"),
                    use_container_width=True,
                )

                nonzero_waste_days = [
                    row for row in res["waste_by_day"] if row["waste_total"] > 1.0
                ]
                if nonzero_waste_days:
                    st.markdown("**Waste by day:**")
                    for row in nonzero_waste_days:
                        st.write(row)

            # ── Raw solver output (collapsible) ──
            with st.expander("🔍 Raw solver output"):
                st.json(res)
