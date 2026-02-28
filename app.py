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
# Styling
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
        .edit-row {
            background: #0e1a14;
            border: 1px solid #2a4a38;
            border-radius: 6px;
            padding: 0.5rem 0.75rem;
            margin-bottom: 0.25rem;
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
    "food_items":   [],
    "people":       50,
    "calories_per_person": 2000,
    "horizon":      60,
    "results":      None,
    "editing_idx":  None,   # index of the row currently being edited, or None
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

RATION_SCENARIOS = {
    "Full (100%)": 1.0,
    "3/4 Ration":  3 / 4,
    "2/3 Ration":  2 / 3,
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

    # ── Demo button — pinned to bottom of sidebar ──
    st.markdown("<div style='flex:1'></div>", unsafe_allow_html=True)
    st.divider()
    st.markdown(
        "<small style='color:#7a9e8a'>Load a pre-built scenario to explore the tool.</small>",
        unsafe_allow_html=True,
    )
    if st.button("🧪 Load Demo Scenario", use_container_width=True):
        st.session_state.people              = 50
        st.session_state.calories_per_person = 2000
        st.session_state.horizon             = 60
        st.session_state.editing_idx         = None
        st.session_state.results             = None
        st.session_state.food_items          = [
            {
                "name":          "Canned Fruit",
                "calories":      600_000,
                "last_day":      5,
                "_cal_per_unit": 150,
                "_units":        4000,
                "_expiry_days":  5,
            },
            {
                "name":          "Fresh Bread",
                "calories":      500_000,
                "last_day":      9,
                "_cal_per_unit": 250,
                "_units":        2000,
                "_expiry_days":  9,
            },
            {
                "name":          "Canned Beans",
                "calories":      800_000,
                "last_day":      None,
                "_cal_per_unit": 400,
                "_units":        2000,
                "_expiry_days":  None,
            },
            {
                "name":          "Dried Rice",
                "calories":      2_700_000,
                "last_day":      None,
                "_cal_per_unit": 3600,
                "_units":        750,
                "_expiry_days":  None,
            },
        ]
        st.rerun()

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
# Section 1 — Food Inventory
# ─────────────────────────────────────────────
st.markdown("## 1 · Food Inventory")

# ── Add food form ──
with st.form("add_food", clear_on_submit=True):
    c1, c2, c3, c4, c5 = st.columns([2, 1.5, 1.5, 1.5, 1])
    name         = c1.text_input("Food / bucket name", placeholder="e.g. Canned Beans")
    cal_per_unit = c2.number_input("Calories per unit", min_value=1, value=200, step=10)
    units        = c3.number_input("Units (cans / items)", min_value=1, value=100, step=1)
    expiry_days  = c4.number_input("Expires in N days (0 = never)", min_value=0, value=0, step=1)
    submitted    = c5.form_submit_button("➕ Add", use_container_width=True)

    if submitted:
        if not name.strip():
            st.warning("Please enter a food name.")
        else:
            st.session_state.food_items.append({
                "name":          name.strip(),
                "calories":      int(cal_per_unit) * int(units),
                "last_day":      int(expiry_days) if expiry_days > 0 else None,
                "_cal_per_unit": int(cal_per_unit),
                "_units":        int(units),
                "_expiry_days":  int(expiry_days) if expiry_days > 0 else None,
            })
            st.session_state.results = None

# ── Inventory table with inline edit ──
if st.session_state.food_items:

    # Column headers
    h1, h2, h3, h4, h5, h6, h7 = st.columns([2.2, 1.2, 1.1, 1.1, 1.4, 0.6, 0.6])
    h1.markdown("**Name**")
    h2.markdown("**Cal / unit**")
    h3.markdown("**Units**")
    h4.markdown("**Total cal**")
    h5.markdown("**Expires (day)**")
    h6.markdown("")   # edit button col
    h7.markdown("")   # delete button col

    st.divider()

    action       = None   # ("delete", idx) | ("edit", idx) | ("save", idx) | ("cancel",)
    edited_vals  = {}

    for i, item in enumerate(st.session_state.food_items):
        is_editing = st.session_state.editing_idx == i

        if is_editing:
            # ── Inline edit row ──
            with st.container():
                e1, e2, e3, e4, e5, e6, e7 = st.columns([2.2, 1.2, 1.1, 1.1, 1.4, 0.6, 0.6])
                new_name = e1.text_input(
                    "Name", value=item["name"], key=f"edit_name_{i}",
                    label_visibility="collapsed"
                )
                new_cpu = e2.number_input(
                    "Cal/unit", value=item["_cal_per_unit"], min_value=1, step=10,
                    key=f"edit_cpu_{i}", label_visibility="collapsed"
                )
                new_units = e3.number_input(
                    "Units", value=item["_units"], min_value=1, step=1,
                    key=f"edit_units_{i}", label_visibility="collapsed"
                )
                # total cal is derived — show it read-only as live preview
                e4.markdown(f"`{new_cpu * new_units:,}`")
                new_exp = e5.number_input(
                    "Expiry", value=item["_expiry_days"] if item["_expiry_days"] else 0,
                    min_value=0, step=1,
                    key=f"edit_exp_{i}", label_visibility="collapsed"
                )
                if e6.button("💾", key=f"save_{i}", help="Save changes"):
                    action = ("save", i, new_name, new_cpu, new_units, new_exp)
                if e7.button("✕", key=f"cancel_{i}", help="Cancel edit"):
                    action = ("cancel",)
        else:
            # ── Static display row ──
            c1, c2, c3, c4, c5, c6, c7 = st.columns([2.2, 1.2, 1.1, 1.1, 1.4, 0.6, 0.6])
            c1.write(item["name"])
            c2.write(f"{item['_cal_per_unit']:,}")
            c3.write(f"{item['_units']:,}")
            c4.write(f"{item['calories']:,}")
            c5.write(item["_expiry_days"] if item["_expiry_days"] else "Never")
            if c6.button("✏️", key=f"edit_{i}", help=f"Edit {item['name']}"):
                action = ("edit", i)
            if c7.button("🗑", key=f"del_{i}", help=f"Delete {item['name']}"):
                action = ("delete", i)

    # ── Process deferred actions (after loop to avoid mid-iteration mutation) ──
    if action:
        kind = action[0]
        if kind == "delete":
            _, idx = action
            st.session_state.food_items.pop(idx)
            st.session_state.editing_idx = None
            st.session_state.results = None
            st.rerun()
        elif kind == "edit":
            _, idx = action
            st.session_state.editing_idx = idx
            st.rerun()
        elif kind == "cancel":
            st.session_state.editing_idx = None
            st.rerun()
        elif kind == "save":
            _, idx, new_name, new_cpu, new_units, new_exp = action
            st.session_state.food_items[idx] = {
                "name":          new_name.strip() or st.session_state.food_items[idx]["name"],
                "calories":      int(new_cpu) * int(new_units),
                "last_day":      int(new_exp) if new_exp > 0 else None,
                "_cal_per_unit": int(new_cpu),
                "_units":        int(new_units),
                "_expiry_days":  int(new_exp) if new_exp > 0 else None,
            }
            st.session_state.editing_idx = None
            st.session_state.results = None
            st.rerun()

    st.divider()
    if st.button("🧹 Clear all inventory"):
        st.session_state.food_items = []
        st.session_state.editing_idx = None
        st.session_state.results = None
        st.rerun()

else:
    st.info("No food items added yet. Use the form above to add inventory.")

st.divider()

# ─────────────────────────────────────────────
# Section 2 — Run optimisation
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
# Section 3 — Results
# ─────────────────────────────────────────────
if st.session_state.results:
    st.divider()
    st.markdown("## 3 · Results")

    # ── Summary stat boxes ──
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

            # ── Daily plan ──
            st.markdown("### Daily Plan")

            survived_schedule = [r for r in res["schedule"] if r["survived"] == 1]

            for row in survived_schedule:
                day = row["day"]

                # Expiry alerts — only on the expiry day itself
                if day in alerts:
                    for alert in alerts[day]:
                        name       = alert["bucket"]
                        extra_u_pp = alert["extra_units_per_person"]
                        remainder  = alert["remainder_units"]
                        extra_cal  = alert["extra_calories"]

                        # Build the message
                        per_person_str = (
                            f"**{extra_u_pp} additional unit{'s' if extra_u_pp != 1 else ''} "
                            f"of {name} per person**"
                        )
                        remainder_str = (
                            f" ({remainder:.1f} units left over for the group)"
                            if remainder >= 0.5 else ""
                        )
                        st.warning(
                            f"⚠️ **{name}** expires today — {extra_cal:,.0f} unscheduled calories "
                            f"available. Each person can consume {per_person_str} before this "
                            f"food is lost.{remainder_str}"
                        )

                # ── Per-day consumption plan (collapsed expander) ──
                plan_rows = []
                for item in st.session_state.food_items:
                    cal_consumed = row.get(item["name"], 0.0)
                    if cal_consumed < 0.5:
                        continue
                    units_consumed = cal_consumed / item["_cal_per_unit"]
                    plan_rows.append({
                        "Food":          item["name"],
                        "Units":         f"{units_consumed:.2f}",
                        "Cal from item": f"{cal_consumed:,.0f}",
                    })

                total_cal = row["total"]
                with st.expander(
                    f"Day {day} — {total_cal:,.0f} cal  "
                    f"({total_cal / st.session_state.people:,.0f} cal/person)",
                    expanded=False,
                ):
                    if plan_rows:
                        st.dataframe(
                            pd.DataFrame(plan_rows).set_index("Food"),
                            use_container_width=True,
                        )
                    else:
                        st.write("No consumption scheduled.")

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
                    r for r in res["waste_by_day"] if r["waste_total"] > 1.0
                ]
                if nonzero_waste_days:
                    st.markdown("**Waste by day:**")
                    for r in nonzero_waste_days:
                        st.write(r)

            # ── Raw solver output ──
            with st.expander("🔍 Raw solver output"):
                st.json(res)