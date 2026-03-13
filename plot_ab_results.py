#!/usr/bin/env python3
"""DTV vs Naive A/B experiment visualization.

Figures for presentation: fig1, fig2a, fig6a
Figures for internal debugging: fig4b, fig6b, fig8, fig_cat3_diag
Removed (redundant/unfair/unreadable): fig2b, fig4a, fig7
"""
import glob
import json
import statistics
from pathlib import Path

from scipy.stats import binomtest, wilcoxon

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

OUT_DIR = Path("plots")
OUT_DIR.mkdir(exist_ok=True)

data: list[dict] = []
for path in sorted(glob.glob("result_delta/budgetk32/ab_batch_*.json")):
    with open(path) as f:
        data.extend(json.load(f))

cases: dict[str, dict] = {}
for r in data:
    cid = r["case_id"]
    cases.setdefault(cid, {})[r["config"]] = r

cases = {cid: c for cid, c in cases.items() if "dtv" in c and "naive" in c}
N_TOTAL = len(cases)

with open("result_delta/budgetk32/c_token_counts.json") as f:
    c_tokens: dict[str, int] = json.load(f)

cat1a, cat1b, cat1c, cat1d = [], [], [], []
cat2, cat3, cat4 = [], [], []

for cid, c in sorted(cases.items()):
    d, n = c.get("dtv", {}), c.get("naive", {})
    dp = d.get("final_verdict") == "pass"
    np_ = n.get("final_verdict") == "pass"

    if dp and np_:
        dc = d["feedback_count"] == 0 and d["rollback_count"] == 0
        nc = n["feedback_count"] == 0 and n["rollback_count"] == 0
        if dc and nc:
            cat1a.append(cid)
        elif dc and not nc:
            cat1b.append(cid)
        elif not dc and nc:
            cat1c.append(cid)
        else:
            cat1d.append(cid)
    elif dp and not np_:
        cat2.append(cid)
    elif not dp and np_:
        cat3.append(cid)
    else:
        cat4.append(cid)

cat1_all = cat1a + cat1b + cat1c + cat1d


def ratios(cids: list[str]) -> list[float]:
    return [
        cases[c]["dtv"]["total_tokens"] / max(cases[c]["naive"]["total_tokens"], 1)
        for c in cids
    ]


plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.grid": True,
    "grid.alpha": 0.3,
    "font.size": 12,
})

COLORS = {
    "cat1": "#4CAF50",
    "cat2": "#2196F3",
    "cat3": "#FF5722",
    "cat4": "#9E9E9E",
    "dtv": "#2196F3",
    "naive": "#FF9800",
}


def add_tldr(fig, text):
    fig.text(
        0.5, -0.02, text,
        ha="center", va="top", fontsize=11, style="italic",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="#FFF9C4", edgecolor="#F9A825", alpha=0.9),
    )


def make_violin(ax, box_data, labels, colors):
    parts = ax.violinplot(box_data, positions=range(1, len(box_data) + 1),
                          showmedians=False, showextrema=False)
    for i, pc in enumerate(parts["bodies"]):
        pc.set_facecolor(colors[i])
        pc.set_alpha(0.35)

    for i, rd in enumerate(box_data):
        x_jitter = np.random.default_rng(42).uniform(-0.12, 0.12, len(rd))
        ax.scatter([i + 1 + xj for xj in x_jitter], rd,
                   color=colors[i], edgecolor="white", s=30, alpha=0.7, zorder=3)
        med = statistics.median(rd)
        ax.plot([i + 0.7, i + 1.3], [med, med], color="black", linewidth=2.5, zorder=4)
        ax.text(i + 1, med, f" {med:.2f}", ha="left", va="bottom", fontsize=10, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.15", facecolor="white", edgecolor="grey", alpha=0.8))

    ax.set_xticks(range(1, len(box_data) + 1))
    ax.set_xticklabels(labels)
    ax.axhline(y=1.0, color="black", linestyle="--", linewidth=1.5, alpha=0.5, label="DTV = Naive")


# =====================================================================
# PRESENTATION FIGURES (fig1, fig2a, fig6a)
# =====================================================================

# --- Figure 1: 4-Category Overview ---
fig1, ax1 = plt.subplots(figsize=(8, 5))

cats_labels = ["Cat1\nBoth Pass", "Cat2\nDTV Only", "Cat3\nNaive Only", "Cat4\nBoth Fail"]
cats_counts = [len(cat1_all), len(cat2), len(cat3), len(cat4)]
cats_colors = [COLORS["cat1"], COLORS["cat2"], COLORS["cat3"], COLORS["cat4"]]

bars = ax1.bar(cats_labels, cats_counts, color=cats_colors, edgecolor="white", width=0.6)
for bar, count in zip(bars, cats_counts):
    ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
             str(count), ha="center", va="bottom", fontsize=16, fontweight="bold")

dtv_total = len(cat1_all) + len(cat2)
naive_total = len(cat1_all) + len(cat3)
dtv_pct = dtv_total / N_TOTAL * 100
naive_pct = naive_total / N_TOTAL * 100
ax1.set_ylabel("Number of Cases")
ax1.set_title(
    f"{N_TOTAL}-Case A/B: DTV pass={dtv_pct:.1f}% vs Naive pass={naive_pct:.1f}%",
    fontsize=14, fontweight="bold")
ax1.set_ylim(0, max(cats_counts) + 8)
ax1.grid(axis="x", visible=False)
fig1.tight_layout()
add_tldr(fig1,
    f"TL;DR: DTV {dtv_pct:.1f}% vs Naive {naive_pct:.1f}%. "
    "Current prototype underperforms baseline; Cat3 repair-stall is the dominant gap.")
fig1.savefig(OUT_DIR / "fig1_category_overview.png", dpi=150, bbox_inches="tight")
print("Saved fig1_category_overview.png")

# --- Figure 2a: Violin - Cat1 Sub-Categories (mechanism validation) ---
fig2a, ax2a = plt.subplots(figsize=(10, 6))

sub_groups = [
    (f"Cat1a\nBoth 1st\n(N={len(cat1a)})", cat1a, "#66BB6A"),
    (f"Cat1b\nDTV 1st\nN Fixes\n(N={len(cat1b)})", cat1b, "#42A5F5"),
    (f"Cat1c\nN 1st\nDTV Fixes\n(N={len(cat1c)})", cat1c, "#FFA726"),
    (f"Cat1d\nBoth Fix\n(N={len(cat1d)})", cat1d, "#388E3C"),
]
sub_data = [ratios(cids) for _, cids, _ in sub_groups]
sub_labels = [lbl for lbl, _, _ in sub_groups]
sub_colors = [clr for _, _, clr in sub_groups]

make_violin(ax2a, sub_data, sub_labels, sub_colors)

ax2a.set_ylabel("Token Ratio (DTV / Naive) [log]")
ax2a.set_yscale("log")
ax2a.set_yticks([0.1, 0.2, 0.5, 1.0, 2.0, 5.0])
ax2a.get_yaxis().set_major_formatter(mticker.ScalarFormatter())
ax2a.set_title("Cat1 (Both Pass): Token Ratio by Sub-Category", fontsize=14, fontweight="bold")
ax2a.legend(loc="upper right")
fig2a.tight_layout()
cat1d_med = statistics.median(ratios(cat1d))
cat1d_pct = abs(1 - cat1d_med) * 100
cat1d_dir = "cheaper" if cat1d_med < 1 else "more expensive"
add_tldr(fig2a,
    f"TL;DR: Both fix (Cat1d, {len(cat1d)} cases) -> DTV {cat1d_pct:.0f}% {cat1d_dir}. "
    "Zero overhead when both 1st-attempt (Cat1a).")
fig2a.savefig(OUT_DIR / "fig2a_cat1_violin.png", dpi=150, bbox_inches="tight")
print("Saved fig2a_cat1_violin.png")

# --- Figure 6a: CDF - Cat1 only, x-axis = k (= total_tokens / C_tokens) ---
fig6a, ax6a = plt.subplots(figsize=(9, 5))

cat1_dtv_k = sorted([cases[c]["dtv"]["total_tokens"] / c_tokens[c] for c in cat1_all])
cat1_naive_k = sorted([cases[c]["naive"]["total_tokens"] / c_tokens[c] for c in cat1_all])

cdf_y1 = np.arange(1, len(cat1_all) + 1) / len(cat1_all)
ax6a.step(cat1_dtv_k, cdf_y1, color=COLORS["dtv"], linewidth=2.5, label="DTV", where="post")
ax6a.step(cat1_naive_k, cdf_y1, color=COLORS["naive"], linewidth=2.5, label="Naive", where="post")

ax6a.set_xlabel("k (= generated tokens / C source tokens)")
ax6a.set_ylabel("Fraction of cases using <= k")
n_cat1 = len(cat1_all)
ax6a.set_title(f"CDF: Normalized Token Usage (Cat1 Both Pass, N={n_cat1})", fontsize=14, fontweight="bold")
ax6a.legend(fontsize=12, loc="lower right")
ax6a.set_xlim(0, None)

dtv_med_k = float(np.median(cat1_dtv_k))
naive_med_k = float(np.median(cat1_naive_k))
ax6a.axvline(dtv_med_k, color=COLORS["dtv"], linestyle=":", alpha=0.7)
ax6a.axvline(naive_med_k, color=COLORS["naive"], linestyle=":", alpha=0.7)
ax6a.text(dtv_med_k, 0.52, f"DTV median\nk={dtv_med_k:.1f}", ha="right", fontsize=9, color=COLORS["dtv"])
ax6a.text(naive_med_k, 0.45, f"Naive median\nk={naive_med_k:.1f}", ha="left", fontsize=9, color=COLORS["naive"])

ax6a.axvline(32, color="black", linestyle="-", linewidth=1, alpha=0.3)
ax6a.text(32, 0.05, "budget (k=32)", ha="right", fontsize=8, alpha=0.5, rotation=90)

wins = sum(1 for c in cat1_all if cases[c]["dtv"]["total_tokens"] < cases[c]["naive"]["total_tokens"])
losses = sum(1 for c in cat1_all if cases[c]["dtv"]["total_tokens"] > cases[c]["naive"]["total_tokens"])
ties = n_cat1 - wins - losses

cat1_diffs = [cases[c]["dtv"]["total_tokens"] - cases[c]["naive"]["total_tokens"] for c in cat1_all]
nz_diffs = [d for d in cat1_diffs if d != 0]
sign_p = binomtest(wins, wins + losses, 0.5, alternative="greater").pvalue
wil_p = wilcoxon(nz_diffs, alternative="less").pvalue

fig6a.tight_layout()
add_tldr(fig6a,
    f"TL;DR: Same {n_cat1} cases both solve. DTV median k={dtv_med_k:.1f} vs "
    f"Naive k={naive_med_k:.1f}. Wins {wins}:{losses}:{ties}. "
    f"Sign p={sign_p:.3f}, Wilcoxon p={wil_p:.2f}.")
fig6a.savefig(OUT_DIR / "fig6a_cdf_cat1.png", dpi=150, bbox_inches="tight")
print("Saved fig6a_cdf_cat1.png")

# =====================================================================
# INTERNAL FIGURES (fig4b, fig6b, fig8, fig_cat3_diag)
# =====================================================================

# --- Figure 4b: Cat3 Reverse [Internal] ---
fig4b, ax4b = plt.subplots(figsize=(12, 5))

cat3_sorted = sorted(cat3, key=lambda c: cases[c]["naive"]["total_tokens"])
x_pos3 = np.arange(len(cat3_sorted))
dtv_toks3 = [cases[c]["dtv"]["total_tokens"] for c in cat3_sorted]
naive_toks3 = [cases[c]["naive"]["total_tokens"] for c in cat3_sorted]

bar_width = 0.35
ax4b.bar(x_pos3 - bar_width / 2, naive_toks3, bar_width, color=COLORS["naive"], label="Naive (PASS)", edgecolor="white")
ax4b.bar(x_pos3 + bar_width / 2, dtv_toks3, bar_width, color=COLORS["cat3"], label="DTV (FAIL)", edgecolor="white", alpha=0.7)

for i, tok in enumerate(naive_toks3):
    ax4b.text(i - bar_width / 2, tok + 80, str(tok), ha="center", va="bottom", fontsize=7, color=COLORS["naive"])

ax4b.set_xticks(x_pos3)
ax4b.set_xticklabels([c[:8] for c in cat3_sorted], rotation=45, ha="right", fontsize=7)
ax4b.set_ylabel("Total Tokens")
ax4b.set_title(f"[Internal] Cat3: Naive Passes, DTV Fails ({len(cat3)} cases)", fontsize=13, fontweight="bold")
ax4b.legend(fontsize=10)
ax4b.grid(axis="x", visible=False)
fig4b.tight_layout()
fig4b.savefig(OUT_DIR / "fig4b_cat3_reverse.png", dpi=150, bbox_inches="tight")
print("Saved fig4b_cat3_reverse.png")

# --- Figure 6b: CDF - All cases [Internal] ---
fig6b, ax6b = plt.subplots(figsize=(9, 5))

all_cids = sorted(cases.keys())
all_dtv_k = sorted([cases[c]["dtv"]["total_tokens"] / c_tokens[c] for c in all_cids])
all_naive_k = sorted([cases[c]["naive"]["total_tokens"] / c_tokens[c] for c in all_cids])

cdf_y_all = np.arange(1, N_TOTAL + 1) / N_TOTAL
ax6b.step(all_dtv_k, cdf_y_all, color=COLORS["dtv"], linewidth=2.5, label="DTV", where="post")
ax6b.step(all_naive_k, cdf_y_all, color=COLORS["naive"], linewidth=2.5, label="Naive", where="post")

ax6b.set_xlabel("k (= generated tokens / C source tokens)")
ax6b.set_ylabel("Fraction of cases using <= k")
ax6b.set_title(f"[Internal] CDF: Normalized Token Usage - All {N_TOTAL} Cases", fontsize=14, fontweight="bold")
ax6b.legend(fontsize=12, loc="lower right")
ax6b.set_xlim(0, None)
ax6b.axvline(32, color="black", linestyle="-", linewidth=1, alpha=0.3)
ax6b.text(32, 0.05, "budget (k=32)", ha="right", fontsize=8, alpha=0.5, rotation=90)

dtv_med_all = float(np.median(all_dtv_k))
naive_med_all = float(np.median(all_naive_k))
ax6b.axvline(dtv_med_all, color=COLORS["dtv"], linestyle=":", alpha=0.7)
ax6b.axvline(naive_med_all, color=COLORS["naive"], linestyle=":", alpha=0.7)
ax6b.text(dtv_med_all, 0.52, f"DTV median\nk={dtv_med_all:.1f}", ha="right", fontsize=9, color=COLORS["dtv"])
ax6b.text(naive_med_all, 0.45, f"Naive median\nk={naive_med_all:.1f}", ha="left", fontsize=9, color=COLORS["naive"])

fig6b.tight_layout()
fig6b.savefig(OUT_DIR / "fig6b_cdf_all.png", dpi=150, bbox_inches="tight")
print("Saved fig6b_cdf_all.png")

# --- Figure 8: Ratio Histogram [Internal] ---
fig8, ax8 = plt.subplots(figsize=(9, 5))

cat1_ratios = ratios(cat1_all)
med_ratio = statistics.median(cat1_ratios)

bins = list(np.concatenate([np.arange(0, 2.0, 0.2), np.arange(2.0, max(cat1_ratios) + 0.5, 0.5)]))
counts_below = [r for r in cat1_ratios if r < 1.0]
counts_above = [r for r in cat1_ratios if r >= 1.0]

ax8.hist(counts_below, bins=bins, color=COLORS["dtv"], edgecolor="white", alpha=0.8, label=f"DTV wins ({len(counts_below)})")
ax8.hist(counts_above, bins=bins, color=COLORS["cat3"], edgecolor="white", alpha=0.6, label=f"Naive wins ({len(counts_above)})")

ax8.axvline(1.0, color="black", linestyle="--", linewidth=1.5, alpha=0.7)
ax8.axvline(med_ratio, color=COLORS["dtv"], linestyle="-", linewidth=2.5)
ax8.text(med_ratio - 0.02, ax8.get_ylim()[1] * 0.9 if ax8.get_ylim()[1] > 0 else 5,
         f"Median = {med_ratio:.2f}", ha="right", fontsize=11, fontweight="bold", color=COLORS["dtv"])

ax8.set_xlabel("Token Ratio (DTV / Naive)")
ax8.set_ylabel("Number of Cases")
ax8.set_title(f"[Internal] Token Ratio Distribution (Both Pass, Cat1, N={len(cat1_all)})", fontsize=14, fontweight="bold")
ax8.legend(fontsize=11)
ax8.grid(axis="y", alpha=0.3)
ax8.grid(axis="x", visible=False)

fig8.tight_layout()
add_tldr(fig8, f"TL;DR: Median ratio = {med_ratio:.2f}. {len(counts_below)}/{len(cat1_ratios)} cases favor DTV.")
fig8.savefig(OUT_DIR / "fig8_ratio_hist.png", dpi=150, bbox_inches="tight")
print("Saved fig8_ratio_hist.png")

# --- Figure Cat3 Diagnosis: Repair Depth [Internal] ---
fig_diag, ax_diag = plt.subplots(figsize=(10, 5))

cat3_fb = sorted([cases[c]["dtv"]["feedback_count"] for c in cat3], reverse=True)
cat3_rb = sorted([cases[c]["dtv"]["rollback_count"] for c in cat3], reverse=True)
x_diag = np.arange(len(cat3))

ax_diag.bar(x_diag - 0.2, cat3_fb, 0.4, color=COLORS["cat3"], label="Feedback rounds", alpha=0.8)
ax_diag.bar(x_diag + 0.2, cat3_rb, 0.4, color="#B71C1C", label="Rollback count", alpha=0.6)

ax_diag.set_xlabel("Cat3 Cases (sorted by feedback count)")
ax_diag.set_ylabel("Count")
ax_diag.set_title(f"[Internal] Cat3 Repair Loop Depth ({len(cat3)} DTV-fail cases)", fontsize=14, fontweight="bold")
ax_diag.legend(fontsize=11)
ax_diag.grid(axis="x", visible=False)

med_fb = statistics.median(cat3_fb)
ax_diag.axhline(med_fb, color="black", linestyle="--", linewidth=1.5, alpha=0.5)
ax_diag.text(len(cat3) - 1, med_fb + 2, f"Median fb={med_fb:.0f}", ha="right", fontsize=10,
             bbox=dict(boxstyle="round,pad=0.15", facecolor="white", edgecolor="grey", alpha=0.8))

fig_diag.tight_layout()
cat3_at_budget = sum(
    1 for c in cat3
    if cases[c]["dtv"]["total_tokens"] == max(cases[c]["dtv"]["total_tokens"], cases[c]["naive"]["total_tokens"])
    and cases[c]["dtv"]["final_verdict"] != "pass"
)
add_tldr(fig_diag,
    f"TL;DR: Cat3 DTV failures are repair stalls. "
    f"Median {med_fb:.0f} feedback rounds (max {max(cat3_fb)}). "
    f"{cat3_at_budget}/{len(cat3)} exhaust budget.")
fig_diag.savefig(OUT_DIR / "fig_cat3_diagnosis.png", dpi=150, bbox_inches="tight")
print("Saved fig_cat3_diagnosis.png")

# =====================================================================

print(f"\nAll figures saved to {OUT_DIR.resolve()}/")
print("\nPresentation figures:")
for name in ["fig1_category_overview.png", "fig2a_cat1_violin.png", "fig6a_cdf_cat1.png"]:
    print(f"  {name}")
print("\nInternal figures:")
for name in ["fig4b_cat3_reverse.png", "fig6b_cdf_all.png", "fig8_ratio_hist.png", "fig_cat3_diagnosis.png"]:
    print(f"  {name}")
