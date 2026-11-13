function dcx_plot_experiments(R, out)
%DCX_PLOT_EXPERIMENTS Figures for the controller comparison (paper / submission).
cols = struct('fixed', [0.45 0.45 0.45], 'empc', [0.13 0.47 0.71], 'haempc', [0.85 0.37 0.01]);
names = struct('fixed', 'Baseline (fixed SP + PI)', 'empc', 'EMPC', 'haempc', 'PI-HA-EMPC');
for sc = fieldnames(R.traces)'
    f = figure('Visible', 'off', 'Position', [100 100 900 650]);
    tl = tiledlayout(f, 3, 1, 'TileSpacing', 'compact');
    title(tl, sprintf('DATACORE-X closed loop — scenario: %s', sc{1}));
    modes = fieldnames(R.traces.(sc{1}))';
    ax = nexttile(tl); hold(ax, 'on');
    for md = modes, d = R.traces.(sc{1}).(md{1}); plot(ax, d.t/3600, d.max_in, 'Color', cols.(md{1}), 'DisplayName', names.(md{1})); end
    yline(ax, 27, '--', 'ASHRAE 27 °C', 'HandleVisibility', 'off'); yline(ax, 28, ':', 'T_{srv} 28 °C', 'HandleVisibility', 'off'); ylabel(ax, 'Max rack inlet (°C)'); legend(ax, 'Location', 'best'); grid(ax, 'on');
    ax = nexttile(tl); hold(ax, 'on');
    for md = modes, d = R.traces.(sc{1}).(md{1}); plot(ax, d.t/3600, d.fac, 'Color', cols.(md{1})); end
    ylabel(ax, 'Facility power (kW)'); grid(ax, 'on');
    ax = nexttile(tl); hold(ax, 'on');
    for md = modes, d = R.traces.(sc{1}).(md{1}); plot(ax, d.t/3600, d.sp(:,1), 'Color', cols.(md{1})); end
    ylabel(ax, 'CHW supply setpoint (°C)'); xlabel(ax, 'Time (h)'); grid(ax, 'on');
    exportgraphics(f, fullfile(out, sprintf('fig_closed_loop_%s.png', sc{1})), 'Resolution', 130);
    close(f);
end
end
