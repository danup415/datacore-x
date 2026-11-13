"""IMS figure: health indicator of every bearing per test (failed ones highlighted) and the
envelope-spectrum evidence (SNR at the expected defect frequency) for each failed bearing."""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import ims_analysis as A
import os
from dcx_paths import FIG

plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
BLUE, ORANGE, RED, GREY = "#2F5A86", "#B7791F", "#B42318", "#A0A6AD"
d = A.load()
tests = sorted(d.test.unique())
fig, ax = plt.subplots(2, len(tests), figsize=(4.4 * len(tests), 6.4), squeeze=False)
for j, t in enumerate(tests):
    a0, a1 = ax[0, j], ax[1, j]
    nf = 0
    for b in range(1, 5):
        g = d[(d.test == t) & (d.bearing == b)].sort_values("time")
        if g.empty:
            continue
        sm, thr, al = A.indicator(g)
        h = (g["time"] - g["time"].iloc[0]).dt.total_seconds().values / 86400
        failed = (t, b) in A.FAILED
        col = (RED, "#6B4C9A")[nf % 2] if failed else GREY
        a0.plot(h, sm, color=col, lw=1.3 if failed else 0.8,
                label=f"B{b}: {A.FAILED[(t, b)]}" if failed else f"B{b}: healthy")
        if failed:
            if al is not None:
                a0.axvline(h[al], color=col, ls="--", lw=1)
                a0.text(0.02, 0.45 - 0.08 * nf, f"B{b} alarm {h[-1] - h[al]:.1f} d before failure", transform=a0.transAxes,
                        color=col, fontsize=7)
            band = A.EXPECT[A.FAILED[(t, b)]]
            snr = g[f"{band}_snr"].rolling(9, min_periods=1).median().values
            a1.plot(h, snr, color=col, lw=1, label=f"B{b}: {band} SNR")
            other = [c for c in ("BPFO", "BPFI", "BSF") if c != band]
            for c in other:
                a1.plot(h, g[f"{c}_snr"].rolling(9, min_periods=1).median().values, color=GREY, lw=0.5, alpha=0.6)
            nf += 1
    a0.set_yscale("log"); a0.set_title(f"IMS test {t}: RMS / healthy baseline"); a0.legend(frameon=False, fontsize=7)
    a0.set_xlabel("Days"); a1.set_xlabel("Days"); a1.set_ylabel("Envelope SNR (dB)")
    a1.set_title("Defect-frequency evidence (grey: other bands)"); a1.legend(frameon=False, fontsize=7)
ax[0, 0].set_ylabel("Health indicator (x baseline)")
fig.suptitle("NASA IMS run-to-failure tests: indicators computed with the DATACORE-X MATLAB toolkit", fontsize=10)
plt.tight_layout()
plt.savefig(os.path.join(FIG, "fig_ims.png"), dpi=150)
print("ok")
