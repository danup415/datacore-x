function [F, S] = vib_features(x, fs, freqs, opts)
%VIB_FEATURES Condition-monitoring features of one vibration snapshot.
%   x      acceleration signal in g (vector)
%   fs     sampling rate (Hz)
%   freqs  struct from vib_bearing_freqs (fr, BPFO, BPFI, BSF, FTF)
%   opts   (optional) struct:
%            band   [f1 f2] envelope band-pass in Hz (default: chosen by spectral kurtosis)
%            tol    relative tolerance around a defect line (default 0.03, allows slip)
%            nharm  harmonics summed per defect frequency (default 3)
%
%   F (scalar struct of features):
%     Time domain:  rms_g, peak_g, crest, kurtosis, skewness, p2p_g
%     Velocity:     vrms_mms   RMS velocity 10-1000 Hz in mm/s (ISO 10816 / 20816 band)
%     Spectrum:     e_lo, e_mid, e_hi    energy fractions 0-1k / 1-5k / >5 kHz
%     Envelope:     env_BPFO, env_BPFI, env_BSF, env_FTF   envelope-spectrum amplitude summed over
%                   nharm harmonics (g), and *_snr in dB over the local envelope noise floor
%                   band_lo, band_hi   envelope band used
%   S (optional): spectra for plotting (f, P, fe, Pe, fv, V).
%
%   The envelope band is the 1/3-octave-ish window with the highest spectral kurtosis
%   (pkurtosis), the standard way to find the resonance bearing impacts excite.
if nargin < 4, opts = struct(); end
tol = getf(opts, 'tol', 0.03); nh = getf(opts, 'nharm', 3);
x = x(:) - mean(x);
N = numel(x);
% ---------------- time domain
F.rms_g = rms(x); F.peak_g = max(abs(x)); F.crest = F.peak_g/F.rms_g;
F.kurtosis = kurtosis(x); F.skewness = skewness(x); F.p2p_g = max(x) - min(x);
% ---------------- velocity RMS 10-1000 Hz (frequency-domain integration)
X = fft(x .* 9.80665);                       % m/s^2
f = (0:N-1)'*fs/N; f(f > fs/2) = f(f > fs/2) - fs;
af = abs(f);
H = zeros(N, 1); m = af >= 10 & af <= 1000;
H(m) = 1 ./ (1i*2*pi*f(m));
v = real(ifft(X .* H));                      % m/s
F.vrms_mms = 1000*rms(v);
% ---------------- band energies
P = abs(X(1:floor(N/2)+1)).^2; fp = f(1:floor(N/2)+1); Pt = sum(P);
F.e_lo = sum(P(fp < 1000))/Pt; F.e_mid = sum(P(fp >= 1000 & fp < 5000))/Pt; F.e_hi = sum(P(fp >= 5000))/Pt;
% ---------------- envelope band
if isfield(opts, 'band') && ~isempty(opts.band)
    band = opts.band;
else
    win = 2^nextpow2(round(fs/400));          % ~ 400 Hz resolution windows
    [sk, fk] = pkurtosis(x, fs, win);
    ok = fk > 4*freqs.BPFI & fk < 0.45*fs;    % above the defect harmonics, below Nyquist
    [~, k] = max(sk .* ok);
    bw = max(fs/40, 6*freqs.BPFI);
    band = [max(fk(k) - bw/2, 2*freqs.BPFI), min(fk(k) + bw/2, 0.49*fs)];
end
F.band_lo = band(1); F.band_hi = band(2);
[Pe, fe] = envspectrum(x, fs, 'Method', 'hilbert', 'Band', band);
% ---------------- defect-frequency amplitudes and their SNR over the envelope floor
names = {'BPFO', 'BPFI', 'BSF', 'FTF'};
for i = 1:numel(names)
    f0 = freqs.(names{i}); if strcmp(names{i}, 'BSF'), f0 = 2*f0; end   % 2xBSF dominates for rolling elements
    a = 0; s = 0;
    for h = 1:nh
        w = fe >= h*f0*(1 - tol) & fe <= h*f0*(1 + tol);
        if any(w), a = a + max(Pe(w)); end
        nb = fe >= h*f0*(1 - 6*tol) & fe <= h*f0*(1 + 6*tol) & ~w;
        if any(nb), s = s + median(Pe(nb)); end
    end
    F.(['env_' names{i}]) = a;
    F.([names{i} '_snr']) = 20*log10(max(a, eps)/max(s, eps));
end
if nargout > 1
    S = struct('f', fp, 'P', P/N^2, 'fe', fe, 'Pe', Pe, 'band', band);
end
end

function v = getf(s, k, d)
if isfield(s, k), v = s.(k); else, v = d; end
end
