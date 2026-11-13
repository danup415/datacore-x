function fig = vib_plot_diagnostics(x, fs, freqs, ttl, opts)
%VIB_PLOT_DIAGNOSTICS Waveform, spectrum and envelope spectrum with bearing defect markers.
%   fig = vib_plot_diagnostics(x, fs, freqs, 'IMS test 2, bearing 1, day 7')
if nargin < 4, ttl = ''; end
if nargin < 5, opts = struct(); end
[F, S] = vib_features(x, fs, freqs, opts);
fig = figure('Color', 'w', 'Position', [100 100 1100 760], 'Visible', 'off');
tl = tiledlayout(fig, 3, 1, 'TileSpacing', 'compact', 'Padding', 'compact');
title(tl, ttl, 'FontWeight', 'bold');
nexttile; t = (0:numel(x)-1)/fs;
plot(t, x, 'Color', [0.18 0.35 0.53]); grid on; xlim([0 min(t(end), 0.5)]);
xlabel('Time (s)'); ylabel('Acceleration (g)');
title(sprintf('RMS %.3f g · kurtosis %.1f · crest %.1f · velocity %.2f mm/s (10-1000 Hz)', ...
    F.rms_g, F.kurtosis, F.crest, F.vrms_mms), 'FontWeight', 'normal');
nexttile; semilogy(S.f, S.P, 'Color', [0.18 0.35 0.53]); grid on; xlim([0 fs/2]);
xlabel('Frequency (Hz)'); ylabel('Power');
xline(S.band(1), '--', 'envelope band', 'Color', [0.72 0.47 0.12]); xline(S.band(2), '--', 'Color', [0.72 0.47 0.12]);
title('Spectrum (envelope band chosen by spectral kurtosis)', 'FontWeight', 'normal');
nexttile; plot(S.fe, S.Pe, 'Color', [0.18 0.35 0.53]); grid on; hold on;
fmax = 4.5*freqs.BPFI; xlim([0 fmax]);
cols = struct('BPFO', [0.71 0.14 0.09], 'BPFI', [0.76 0.25 0.05], 'BSF', [0.18 0.49 0.31], 'FTF', [0.37 0.40 0.44]);
nm = fieldnames(cols);
for i = 1:numel(nm)
    f0 = freqs.(nm{i}); lab = nm{i};
    if strcmp(nm{i}, 'BSF'), f0 = 2*f0; lab = '2xBSF'; end
    for h = 1:3
        if h*f0 < fmax
            xl = xline(h*f0, ':', sprintf('%dx%s', h, lab), 'Color', cols.(nm{i}), 'LineWidth', 1.2);
            xl.LabelOrientation = 'horizontal'; xl.FontSize = 8;
        end
    end
end
xlabel('Frequency (Hz)'); ylabel('Envelope amplitude (g)');
title(sprintf('Envelope spectrum · SNR over floor: BPFO %.1f dB, BPFI %.1f dB, 2xBSF %.1f dB', ...
    F.BPFO_snr, F.BPFI_snr, F.BSF_snr), 'FontWeight', 'normal');
end
