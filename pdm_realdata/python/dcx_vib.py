"""DATACORE-X vibration toolkit (Python twin of matlab/vibration/vib_features.m).

Same definitions as the MATLAB functions so the two can be cross-checked on identical files:
  bearing_freqs(n, d, D, theta_deg, rpm)  -> dict fr, BPFO, BPFI, BSF, FTF (Hz)
  features(x_g, fs, freqs, band=None)     -> dict of condition indicators

Indicators
  rms_g, peak_g, crest, kurtosis, skewness, p2p_g     time domain (acceleration in g)
  vrms_mms                                            RMS velocity 10-1000 Hz (ISO 10816/20816 band)
  e_lo, e_mid, e_hi                                   spectral energy fractions <1k, 1-5k, >5k Hz
  env_<D>, <D>_snr                                    envelope-spectrum amplitude at defect frequency D
                                                      (3 harmonics, +-3 % for slip) and its dB over the
                                                      local envelope floor; BSF is evaluated at 2xBSF
  band_lo, band_hi                                    envelope band (max spectral kurtosis)
"""
from __future__ import annotations

import numpy as np
from scipy.signal import hilbert, butter, sosfiltfilt, stft
from scipy.stats import kurtosis as _kurt, skew as _skew

G = 9.80665


def bearing_freqs(n: float, d: float, D: float, theta_deg: float, rpm: float) -> dict:
    fr = rpm / 60.0
    r = d / D * np.cos(np.radians(theta_deg))
    f = {"fr": fr, "BPFO": n / 2 * fr * (1 - r), "BPFI": n / 2 * fr * (1 + r),
         "BSF": D / (2 * d) * fr * (1 - r ** 2), "FTF": fr / 2 * (1 - r)}
    for k in ("BPFO", "BPFI", "BSF", "FTF"):
        f["x" + k] = f[k] / fr
    return f


def spectral_kurtosis_band(x: np.ndarray, fs: float, freqs: dict) -> tuple[float, float]:
    nper = int(2 ** np.ceil(np.log2(fs / 400)))
    nper = min(nper, len(x) // 4)
    f, _, Z = stft(x, fs=fs, nperseg=nper, noverlap=nper // 2, boundary=None)
    A = np.abs(Z) ** 2
    sk = np.mean(A ** 2, axis=1) / np.maximum(np.mean(A, axis=1) ** 2, 1e-30) - 2.0
    ok = (f > 4 * freqs["BPFI"]) & (f < 0.45 * fs)
    if not ok.any():
        ok = f > 0
    k = np.argmax(np.where(ok, sk, -np.inf))
    bw = max(fs / 40, 6 * freqs["BPFI"])
    return max(f[k] - bw / 2, 2 * freqs["BPFI"]), min(f[k] + bw / 2, 0.49 * fs)


def envelope_spectrum(x: np.ndarray, fs: float, band: tuple[float, float]):
    sos = butter(4, [band[0], band[1]], btype="bandpass", fs=fs, output="sos")
    y = sosfiltfilt(sos, x)
    env = np.abs(hilbert(y))
    env = env - env.mean()
    N = len(env)
    E = np.abs(np.fft.rfft(env)) / N * 2
    fe = np.fft.rfftfreq(N, 1 / fs)
    return fe, E


def features(x, fs: float, freqs: dict, band=None, tol: float = 0.03, nharm: int = 3) -> dict:
    x = np.asarray(x, dtype=float)
    x = x - x.mean()
    N = len(x)
    F: dict = {}
    F["rms_g"] = float(np.sqrt(np.mean(x ** 2)))
    F["peak_g"] = float(np.max(np.abs(x)))
    F["crest"] = F["peak_g"] / max(F["rms_g"], 1e-12)
    F["kurtosis"] = float(_kurt(x, fisher=False))
    F["skewness"] = float(_skew(x))
    F["p2p_g"] = float(x.max() - x.min())
    # velocity RMS 10-1000 Hz by frequency-domain integration
    X = np.fft.fft(x * G)
    f = np.fft.fftfreq(N, 1 / fs)
    H = np.zeros(N, dtype=complex)
    m = (np.abs(f) >= 10) & (np.abs(f) <= 1000)
    H[m] = 1 / (1j * 2 * np.pi * f[m])
    v = np.real(np.fft.ifft(X * H))
    F["vrms_mms"] = float(1000 * np.sqrt(np.mean(v ** 2)))
    P = np.abs(X[: N // 2 + 1]) ** 2
    fp = np.abs(f[: N // 2 + 1])
    Pt = P.sum()
    F["e_lo"] = float(P[fp < 1000].sum() / Pt)
    F["e_mid"] = float(P[(fp >= 1000) & (fp < 5000)].sum() / Pt)
    F["e_hi"] = float(P[fp >= 5000].sum() / Pt)
    if band is None:
        band = spectral_kurtosis_band(x, fs, freqs)
    F["band_lo"], F["band_hi"] = float(band[0]), float(band[1])
    fe, E = envelope_spectrum(x, fs, band)
    for name in ("BPFO", "BPFI", "BSF", "FTF"):
        f0 = freqs[name] * (2 if name == "BSF" else 1)
        a = s = 0.0
        for h in range(1, nharm + 1):
            w = (fe >= h * f0 * (1 - tol)) & (fe <= h * f0 * (1 + tol))
            if w.any():
                a += E[w].max()
            nb = (fe >= h * f0 * (1 - 6 * tol)) & (fe <= h * f0 * (1 + 6 * tol)) & ~w
            if nb.any():
                s += np.median(E[nb])
        F["env_" + name] = float(a)
        F[name + "_snr"] = float(20 * np.log10(max(a, 1e-15) / max(s, 1e-15)))
    return F
