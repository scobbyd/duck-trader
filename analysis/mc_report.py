#!/usr/bin/env python3
"""Render the market-character tables from data/mc/market_character.json.

Every number in data/market_character_2024_2026.md comes out of here, so the
prose can be checked against a fresh run. European number formatting per repo
convention: thousands separator ".", decimal comma.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MC = HERE / "cache"
J = MC / "market_character.json"
M = MC / "mechanism.json"

YEARS = ["2023", "2024", "2025", "2026"]


def eu(x, nd=2):
    if x is None:
        return "—"
    try:
        x = float(x)
    except (TypeError, ValueError):
        return str(x)
    if x != x:
        return "—"
    s = f"{x:,.{nd}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def table(head, rows, align=None):
    align = align or (["---"] + ["---:"] * (len(head) - 1))
    out = ["| " + " | ".join(head) + " |", "|" + "|".join(align) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def get(d, *path, default=None):
    for p in path:
        if not isinstance(d, dict) or p not in d:
            return default
        d = d[p]
    return d


def main():
    res = json.loads(J.read_text())
    mech = json.loads(M.read_text()) if M.exists() else {}
    disp = res.get("dispersion", {})
    money = res.get("money", {})
    pred = res.get("predict", {})
    fixed = money.get("_fixed_reactive", "imb_react_0.25_0.75")
    out = []
    P = out.append

    def yr_labels(block, prefix="Y"):
        return [y for y in YEARS if f"{prefix}{y}" in block]

    # ---- money, full years
    per = money.get("by_period", {})
    strat = [("imb_perfect", "imbalance, perfect foresight (ceiling)"),
             (fixed, "imbalance, causal reactive rule (fixed params)"),
             ("imb_react_best", "imbalance, best reactive in hindsight"),
             ("imb_react_live_bound", "imbalance, reactive with live-price bound"),
             ("da_rolling", "day-ahead, rolling 13:00 plan (implementable)")]

    def best_react(label):
        cands = [(k, v) for k, v in per.items()
                 if k.startswith("imb_react_") and "live" not in k
                 and label in v]
        if not cands:
            return None
        return max((v[label] for _, v in cands), key=lambda x: x["cash_eur"])

    for tag, prefix, title in (("year", "Y", "Full calendar years"),
                               ("season", "S", "Mar-Aug only (seasonal control)")):
        labs = [y for y in YEARS if any(f"{prefix}{y}" in v for v in per.values())]
        rows = []
        for key, name in strat:
            r = []
            for y in labs:
                lab = f"{prefix}{y}"
                v = best_react(lab) if key == "imb_react_best" else get(per, key, lab)
                r.append(eu(v["eur_per_year"], 0) if v else "—")
            rows.append([name] + r)
        P(f"### Money, {title} (EUR/year, raw prices, wear excluded)\n")
        P(table(["strategy"] + labs, rows))
        P("")
        # ratio row
        rows = []
        for y in labs:
            lab = f"{prefix}{y}"
            a = get(per, "imb_perfect", lab)
            d = get(per, "da_rolling", lab)
            f_ = get(per, fixed, lab)
            rows.append([y,
                         eu(a["eur_per_year"] / d["eur_per_year"], 2) if a and d else "—",
                         eu(f_["eur_per_year"] / d["eur_per_year"], 2) if f_ and d else "—",
                         eu(a["efc_per_year"], 0) if a else "—",
                         eu(f_["efc_per_year"], 0) if f_ else "—",
                         eu(d["efc_per_year"], 0) if d else "—"])
        P(f"### Ratios and cycling, {title}\n")
        P(table(["period", "imb ceiling / DA", "imb reactive / DA",
                 "EFC/yr imb PF", "EFC/yr imb reactive", "EFC/yr DA"], rows))
        P("")

    # ---- dispersion
    imb = disp.get("imbalance", {})
    da = disp.get("day_ahead", {})
    for prefix, title in (("Y", "Full calendar years"),
                          ("S", "Mar-Aug only")):
        labs = [y for y in YEARS if f"{prefix}{y}" in imb]
        if not labs:
            continue
        metrics = [
            ("sell_mean", "mean sell price", 1),
            ("sell_sd", "sd of sell price", 1),
            ("sell_iqr", "IQR of sell price", 1),
            ("daily_range_sell_mean", "mean daily max-min", 1),
            ("best2h_spread_mean", "mean best-2h spread", 1),
            ("best2h_spread_median", "median best-2h spread", 1),
            ("step_abs_diff_mean", "mean abs ISP-to-ISP step", 1),
            ("sell_neg_pct", "% ISPs sell <= 0", 1),
            ("sell_abs_gt200_pct", "% abs(sell) > 200", 2),
            ("sell_abs_gt500_pct", "% abs(sell) > 500", 2),
            ("dual_priced_pct", "% dual-priced (buy > sell)", 1),
            ("dual_spread_mean_all", "mean buy-sell wedge", 1),
            ("dev_vs_da_mad", "mean abs (imb - DA)", 1),
            ("dev_vs_da_mean", "mean (imb - DA)", 1),
            ("corr_sell_da", "corr(imb sell, DA)", 3),
        ]
        rows = [[name] + [eu(get(imb, f"{prefix}{y}", k), nd) for y in labs]
                for k, name, nd in metrics]
        P(f"### Imbalance dispersion, {title} (EUR/MWh unless stated)\n")
        P(table(["metric"] + labs, rows))
        P("")
        rows = []
        for k, name, nd in [("sell_mean", "mean DA price", 1),
                            ("sell_sd", "sd of DA price", 1),
                            ("daily_range_sell_mean", "mean daily max-min", 1),
                            ("best2h_spread_mean", "mean best-2h spread", 1),
                            ("sell_neg_pct", "% slots DA <= 0", 1)]:
            rows.append([name] + [eu(get(da, f"{prefix}{y}", k), nd) for y in labs])
        P(f"### Day-ahead dispersion, {title} (EUR/MWh)\n")
        P(table(["metric"] + labs, rows))
        P("")

    # ---- level-normalised opportunity (kills the price-level explanation)
    labs = [y for y in YEARS if f"Y{y}" in imb and f"Y{y}" in da]
    if labs:
        rows = []
        for nm, blk in (("imbalance", imb), ("day-ahead", da)):
            r = []
            for y in labs:
                sp = get(blk, f"Y{y}", "best2h_spread_mean")
                lvl = get(da, f"Y{y}", "sell_mean")
                r.append(eu(sp / lvl, 2) if sp and lvl else "—")
            rows.append([f"{nm} best-2h spread / mean DA level"] + r)
        rows.append(["mean DA price level (EUR/MWh)"]
                    + [eu(get(da, f"Y{y}", "sell_mean"), 1) for y in labs])
        P("### Opportunity normalised by the price level, full years\n")
        P(table(["metric"] + labs, rows))
        P("")

    # ---- regulation state
    labs = [y for y in YEARS if f"Y{y}" in imb]
    if labs:
        states = ["-1", "0", "1", "2"]
        rows = [[f"state {s}"] + [eu(get(imb, f"Y{y}", "reg_state_pct", s), 1)
                                  for y in labs] for s in states]
        P("### Regulation-state mix, % of ISPs, full years\n")
        P(table(["state"] + labs, rows))
        P("")

    # ---- predictability
    labs = [y for y in YEARS if f"Y{y}" in pred]
    if labs:
        metrics = [("acf_sell_15min", "ACF lag 15 min", 3),
                   ("acf_sell_30min", "ACF lag 30 min", 3),
                   ("acf_sell_60min", "ACF lag 60 min", 3),
                   ("acf_sell_120min", "ACF lag 2 h", 3),
                   ("ar1_r2_level", "AR(1) R2, price level", 3),
                   ("ar1_r2_dev_vs_da", "AR(1) R2, deviation from DA", 3),
                   ("persistence_skill_level", "persistence skill vs mean", 3),
                   ("p_neg_stays_neg", "P(next ISP also <= 0 | <= 0)", 3),
                   ("mean_neg_run_isps", "mean run length of sell <= 0 (ISPs)", 2),
                   ("p_same_tercile", "P(same price tercile as previous ISP)", 3)]
        rows = [[name] + [eu(get(pred, f"Y{y}", k), nd) for y in labs]
                for k, name, nd in metrics]
        P("### Predictability of the imbalance price, full years\n")
        P(table(["metric"] + labs, rows))
        P("")

    # ---- quarterly money series (structural-break view)
    qlabs = sorted({k for v in per.values() for k in v if k.startswith("Q")})
    if qlabs:
        rows = []
        for q in qlabs:
            a = get(per, "imb_perfect", q)
            f_ = get(per, fixed, q)
            d = get(per, "da_rolling", q)
            rows.append([q[1:].replace("Q", " Q"),
                         eu(a["eur_per_year"], 0) if a else "—",
                         eu(f_["eur_per_year"], 0) if f_ else "—",
                         eu(d["eur_per_year"], 0) if d else "—",
                         eu(a["eur_per_year"] / d["eur_per_year"], 2)
                         if a and d else "—",
                         eu(get(imb, q, "best2h_spread_mean"), 1),
                         eu(get(imb, q, "dual_priced_pct"), 1)])
        P("### Quarterly series (EUR/year run-rate; spread and dual share from the same quarter)\n")
        P(table(["quarter", "imb ceiling", "imb reactive", "DA rolling",
                 "imb/DA", "best-2h spread", "% dual"], rows))
        P("")

    # ---- reactive grid sensitivity
    rows = []
    grid_keys = sorted(k for k in per if k.startswith("imb_react_")
                       and "live" not in k)
    labs = [y for y in YEARS if any(f"Y{y}" in per[k] for k in grid_keys)]
    for k in grid_keys:
        band = k.replace("imb_react_", "").replace("_", "/")
        rows.append([band] + [eu(get(per, k, f"Y{y}", "eur_per_year"), 0)
                              for y in labs])
    if rows:
        P("### Reactive-rule parameter sweep (EUR/year, full years)\n")
        P(table(["quantile band"] + labs, rows))
        P("")

    # ---- controls
    rows = []
    labs = [y for y in YEARS if f"Y{y}" in per.get("imb_perfect", {})]
    for k, name in (("imb_perfect", "imbalance PF, 15-min, dual pricing"),
                    ("imb_perfect_singleprice", "imbalance PF, dual-pricing wedge removed"),
                    ("imb_perfect_hourly_ctrl", "imbalance PF, hourly-averaged prices"),
                    ("da_rolling", "day-ahead rolling, hourly MTU"),
                    ("da_rolling_q15", "day-ahead rolling, 15-min MTU")):
        if k not in per:
            continue
        rows.append([name] + [eu(get(per, k, f"Y{y}", "eur_per_year"), 0)
                              for y in labs])
    P("### Controls (EUR/year, full years)\n")
    P(table(["run"] + labs, rows))
    P("")

    # ---- mechanism probes
    if mech:
        ag = get(mech, "intrahour", "_aggregate", default={})
        labs = [y for y in YEARS if y in ag.get("imbalance_sell", {})]
        rows = [["imbalance, within-hour sd"]
                + [eu(ag["imbalance_sell"].get(y), 1) for y in labs],
                ["day-ahead, within-hour sd"]
                + [eu(ag["day_ahead"].get(y), 1) for y in labs]]
        P("### Intra-hour price structure (EUR/MWh, mean within-hour sd)\n")
        P(table(["market"] + labs, rows))
        P("")
        P("Before / after the 2025-10-01 switch to a 15-minute day-ahead MTU: "
          f"imbalance {eu(ag['imbalance_sell']['pre_15min_mtu'], 1)} -> "
          f"{eu(ag['imbalance_sell']['post_15min_mtu'], 1)}; "
          f"day-ahead {eu(ag['day_ahead']['pre_15min_mtu'], 1)} -> "
          f"{eu(ag['day_ahead']['post_15min_mtu'], 1)}.\n")

        dc = mech.get("dual_cost", {})
        labs = [y for y in YEARS if y in dc]
        rows = [[n] + [eu(dc[y][k], nd) for y in labs] for k, n, nd in (
            ("dual_pct", "% of ISPs dual-priced", 1),
            ("wedge_mean_when_dual", "mean wedge when dual (EUR/MWh)", 1),
            ("wedge_median_when_dual", "median wedge when dual (EUR/MWh)", 1),
            ("wedge_mean_all_eur_mwh", "mean wedge over all ISPs (EUR/MWh)", 1),
            ("eur_per_efc_at_mean_wedge", "wedge cost per full cycle (EUR)", 3),
            ("eur_per_year_at_300_efc", "wedge cost at 300 EFC/yr (EUR)", 0))]
        P("### The dual-pricing wedge, full years\n")
        P(table(["metric"] + labs, rows))
        P("")

        dk = mech.get("decomp", {})
        labs = [y for y in YEARS if y in dk]
        rows = [[n] + [eu(dk[y][k], nd) for y in labs] for k, n, nd in (
            ("best2h_mean", "mean best-2h spread", 1),
            ("best2h_median", "median", 1),
            ("best2h_p25", "p25", 1),
            ("best2h_p75", "p75", 1),
            ("best2h_mean_winsorised_200", "mean, prices clipped to +-200", 1),
            ("tail_contribution", "tail contribution (mean - clipped)", 1),
            ("tail_share_pct", "tail share of the spread, %", 1),
            ("days_below_100", "% of days with spread < 100", 1))]
        P("### Body versus tail of the daily imbalance spread (EUR/MWh)\n")
        P(table(["metric"] + labs, rows))
        P("")

    txt = "\n".join(out)
    (MC / "tables.md").write_text(txt)
    print(txt)


if __name__ == "__main__":
    main()
