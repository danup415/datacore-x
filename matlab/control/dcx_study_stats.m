function S = dcx_study_stats(opts)
%DCX_STUDY_STATS Statistics, tables and figures for the PI-HA-EMPC study.
%   Reads control/results/study/runs_<plan>.csv and writes to
%   control/results/study/{tables,figures}:
%     E1  energy/thermal (normal scenario): mean +- 95 % CI per controller and
%         paired differences vs the baseline (t-interval, Wilcoxon signed-rank)
%     E2  fault scenarios: unplanned-trip rate (Wilson 95 % CI), zone-C/D risk
%         exposure, time > 28 C, energy
%     E3  ablations vs full PI-HA-EMPC (paired by climate/scenario/seed)
%     E4  RUL-estimation-error sensitivity
%     E6  mpcmove solve time
arguments
    opts.Plan (1,1) string = "full"
end
here = fileparts(mfilename('fullpath')); base = fullfile(here, 'results', 'study');
tdir = fullfile(base, 'tables'); fdir = fullfile(base, 'figures');
if ~isfolder(tdir), mkdir(tdir); end
if ~isfolder(fdir), mkdir(fdir); end
R = readtable(fullfile(base, sprintf('runs_%s.csv', opts.Plan)), 'TextType', 'string');
R.co2_kg = R.energy_kwh.*arrayfun(@gridef, R.climate);
modes = ["fixed" "empc" "haempc"]; mlab = ["Baseline (fixed SP + PI)" "EMPC" "PI-HA-EMPC"];
S = struct();

% ============================================================ E1
E1 = R(R.experiment == "E1E2" & R.scenario == "normal", :);
metrics = ["energy_kwh" "cooling_kwh" "pue" "co2_kg" "t_above_28_s" "peak_inlet_c"];
rows = {};
for cl = unique(E1.climate)'
    for wl = ["all" unique(E1.workload)']
        sub = E1(E1.climate == cl & (wl == "all" | E1.workload == wl), :);
        for k = 1:numel(modes)
            x = sub(sub.mode == modes(k), :);
            r = {cl, wl, modes(k), height(x)};
            for m = metrics, [mu, lo, hi] = tci(x.(m)); r = [r, {mu, lo, hi}]; end %#ok<AGROW>
            rows(end+1, :) = r; %#ok<AGROW>
        end
    end
end
vn = {'climate','workload','mode','n'};
for m = metrics, vn = [vn, {char(m), [char(m) '_lo'], [char(m) '_hi']}]; end %#ok<AGROW>
S.E1 = cell2table(rows, 'VariableNames', vn);
writetable(S.E1, fullfile(tdir, 'E1_summary.csv'));
% paired differences
S.E1diff = pairdiff(E1, ["climate" "workload" "seed"], [["empc" "fixed"]; ["haempc" "fixed"]; ["haempc" "empc"]], ...
    ["energy_kwh" "cooling_kwh" "pue" "co2_kg" "t_above_28_s"], ["climate"]);
writetable(S.E1diff, fullfile(tdir, 'E1_paired.csv'));

% ============================================================ E2
E2 = R(R.experiment == "E1E2" & R.scenario ~= "normal", :);
rows = {};
for sc = ["chiller" "pump"]
    for cl = unique(E2.climate)'
        for k = 1:numel(modes)
            x = E2(E2.scenario == sc & E2.climate == cl & E2.mode == modes(k), :);
            [p, plo, phi] = wilson(sum(x.unplanned_trips > 0), height(x));
            [er, erl, erh] = tci(x.risk_zoneCD_s/60); [t28, t28l, t28h] = tci(x.t_above_28_s/60);
            [e, el, eh] = tci(x.energy_kwh);
            rows(end+1, :) = {sc, cl, modes(k), height(x), sum(x.unplanned_trips > 0), p, plo, phi, er, erl, erh, ...
                t28, t28l, t28h, e, el, eh, mean(x.precool_min)}; %#ok<AGROW>
        end
    end
end
S.E2 = cell2table(rows, 'VariableNames', {'scenario','climate','mode','n','n_trip','trip_rate','trip_lo','trip_hi', ...
    'risk_min','risk_lo','risk_hi','t28_min','t28_lo','t28_hi','energy_kwh','energy_lo','energy_hi','precool_min'});
writetable(S.E2, fullfile(tdir, 'E2_faults.csv'));
S.E2diff = pairdiff(E2, ["climate" "workload" "scenario" "seed"], [["haempc" "empc"]; ["haempc" "fixed"]], ...
    ["energy_kwh" "risk_zoneCD_s" "t_above_28_s" "unplanned_trips"], ["scenario"]);
writetable(S.E2diff, fullfile(tdir, 'E2_paired.csv'));

% ============================================================ E3 ablations (+ full HA from E1E2, diurnal)
abl = ["haempc" "ha_noHI" "ha_noRUL" "ha_noPrecool" "empc"];
E3 = R((R.experiment == "E3" | (R.experiment == "E1E2" & ismember(R.mode, ["haempc" "empc"]))) & ...
       R.workload == "diurnal" & R.scenario ~= "normal" & R.rul_scale == 1, :);
rows = {};
for sc = ["chiller" "pump" "all"]
    for k = 1:numel(abl)
        x = E3(E3.mode == abl(k) & (sc == "all" | E3.scenario == sc), :);
        if isempty(x), continue; end
        [p, plo, phi] = wilson(sum(x.unplanned_trips > 0), height(x));
        [er, erl, erh] = tci(x.risk_zoneCD_s/60); [e, el, eh] = tci(x.energy_kwh); [t28, t28l, t28h] = tci(x.t_above_28_s/60);
        [pk, pkl, pkh] = tci(x.peak_inlet_c);
        rows(end+1, :) = {sc, abl(k), height(x), sum(x.unplanned_trips > 0), p, plo, phi, er, erl, erh, e, el, eh, t28, t28l, t28h, pk, pkl, pkh}; %#ok<AGROW>
    end
end
S.E3 = cell2table(rows, 'VariableNames', {'scenario','variant','n','n_trip','trip_rate','trip_lo','trip_hi','risk_min','risk_lo','risk_hi', ...
    'energy_kwh','energy_lo','energy_hi','t28_min','t28_lo','t28_hi','peak_c','peak_lo','peak_hi'});
writetable(S.E3, fullfile(tdir, 'E3_ablation.csv'));

% ============================================================ E4 RUL error
E4 = R(R.climate == "pune" & R.workload == "diurnal" & R.mode == "haempc" & R.scenario ~= "normal" & ...
       (R.experiment == "E4" | R.experiment == "E1E2"), :);
rows = {};
for sc = ["chiller" "pump"]
    for rs = unique(E4.rul_scale)'
        x = E4(E4.scenario == sc & E4.rul_scale == rs, :);
        [p, plo, phi] = wilson(sum(x.unplanned_trips > 0), height(x));
        [er, erl, erh] = tci(x.risk_zoneCD_s/60); [e, el, eh] = tci(x.energy_kwh); [pc, pcl, pch] = tci(x.precool_min);
        rows(end+1, :) = {sc, rs, 100*(rs - 1), height(x), p, plo, phi, er, erl, erh, e, el, eh, pc, pcl, pch}; %#ok<AGROW>
    end
end
S.E4 = cell2table(rows, 'VariableNames', {'scenario','rul_scale','rul_error_pct','n','trip_rate','trip_lo','trip_hi', ...
    'risk_min','risk_lo','risk_hi','energy_kwh','energy_lo','energy_hi','precool_min','precool_lo','precool_hi'});
writetable(S.E4, fullfile(tdir, 'E4_rul_error.csv'));

% ============================================================ E6 solve time
mpc = R(R.mode ~= "fixed" & ~isnan(R.solve_ms_mean), :);
rows = {};
for md = unique(mpc.mode)'
    x = mpc(mpc.mode == md, :);
    rows(end+1, :) = {md, height(x), sum(x.n_solves), sum(x.solve_ms_mean.*x.n_solves)/sum(x.n_solves), median(x.solve_ms_p95), max(x.solve_ms_max)}; %#ok<AGROW>
end
S.E6 = cell2table(rows, 'VariableNames', {'mode','runs','solves','mean_ms','median_run_p95_ms','max_ms'});
writetable(S.E6, fullfile(tdir, 'E6_solve_time.csv'));
S.wall = struct('total_h', sum(R.wall_s)/3600, 'runs', height(R));

% ============================================================ LaTeX tables
latex_E1(S, fullfile(tdir, 'tab_E1.tex'), mlab, modes);
latex_E2(S, fullfile(tdir, 'tab_E2.tex'), mlab, modes);
latex_E3(S, fullfile(tdir, 'tab_E3.tex'));
latex_E4(S, fullfile(tdir, 'tab_E4.tex'));
latex_E6(S, fullfile(tdir, 'tab_E6.tex'));

% ============================================================ figures
figs_study(S, R, fdir, modes, mlab);
save(fullfile(base, sprintf('stats_%s.mat', opts.Plan)), 'S');
fprintf('[stats] %d runs, %.1f CPU-hours. Tables -> %s\n', height(R), S.wall.total_h, tdir);
end

% ======================================================================
function ef = gridef(cl)
if cl == "frankfurt", ef = 0.363; else, ef = 0.727; end   % UBA 2024 DE mix; CEA v20.0 FY2023-24 India
end

function [m, lo, hi] = tci(x)
x = x(~isnan(x)); n = numel(x); m = mean(x);
if n < 2, lo = m; hi = m; return; end
h = tinv(0.975, n - 1)*std(x)/sqrt(n); lo = m - h; hi = m + h;
end

function [p, lo, hi] = wilson(k, n)
if n == 0, p = NaN; lo = NaN; hi = NaN; return; end
z = 1.959964; p = k/n; d = 1 + z^2/n;
c = (p + z^2/(2*n))/d; h = z*sqrt(p*(1 - p)/n + z^2/(4*n^2))/d;
lo = max(0, c - h); hi = min(1, c + h);
end

function T = pairdiff(D, keys, pairs, metrics, groupby)
rows = {};
grp = unique(D(:, cellstr(groupby)), 'rows');
grp = [grp; array2table(repmat("all", 1, numel(groupby)), 'VariableNames', cellstr(groupby))];
for g = 1:height(grp)
    mask = true(height(D), 1);
    for gb = groupby
        if grp.(gb)(g) ~= "all", mask = mask & D.(gb) == grp.(gb)(g); end
    end
    sub = D(mask, :);
    for i = 1:size(pairs, 1)
        A = sub(sub.mode == pairs(i, 1), :); B = sub(sub.mode == pairs(i, 2), :);
        [~, ia, ib] = intersect(join_keys(A, keys), join_keys(B, keys));
        for m = metrics
            d = A.(m)(ia) - B.(m)(ib); [mu, lo, hi] = tci(d);
            bm = mean(B.(m)(ib)); rel = 100*mean(d)/bm; rlo = 100*lo/bm; rhi = 100*hi/bm;
            if all(d == 0), p = 1; else, p = signrank(d); end
            r = {}; for gb = groupby, r = [r, {grp.(gb)(g)}]; end %#ok<AGROW>
            rows(end+1, :) = [r, {pairs(i, 1) + " - " + pairs(i, 2), m, numel(d), bm, mu, lo, hi, rel, rlo, rhi, p}]; %#ok<AGROW>
        end
    end
end
T = cell2table(rows, 'VariableNames', [cellstr(groupby), {'comparison','metric','n','base_mean','mean_diff','ci_lo','ci_hi','rel_pct','rel_lo','rel_hi','p_wilcoxon'}]);
end

function k = join_keys(T, keys)
k = strings(height(T), 1);
for c = keys, k = k + "|" + string(T.(c)); end
end

function s = pm(m, lo, hi, fmt)
s = sprintf([fmt ' {\\scriptsize[' fmt ', ' fmt ']}'], m, lo, hi);
end

function latex_E1(S, f, mlab, modes)
fid = fopen(f, 'w'); c = onCleanup(@() fclose(fid));
fprintf(fid, '%% generated by dcx_study_stats.m\n\\begin{tabular}{llrrrr}\n\\toprule\n');
fprintf(fid, 'Climate & Controller & Facility energy (kWh) & Cooling energy (kWh) & PUE & Time $>$28\\,\\textdegree C (min)\\\\\n\\midrule\n');
for cl = ["pune" "frankfurt"]
    for k = 1:3
        x = S.E1(S.E1.climate == cl & S.E1.workload == "all" & S.E1.mode == modes(k), :);
        if isempty(x), continue; end
        fprintf(fid, '%s & %s & %s & %s & %s & %s\\\\\n', ternary(k == 1, capital(cl), ""), mlab(k), ...
            pm(x.energy_kwh, x.energy_kwh_lo, x.energy_kwh_hi, '%.1f'), pm(x.cooling_kwh, x.cooling_kwh_lo, x.cooling_kwh_hi, '%.1f'), ...
            pm(x.pue, x.pue_lo, x.pue_hi, '%.3f'), pm(x.t_above_28_s/60, x.t_above_28_s_lo/60, x.t_above_28_s_hi/60, '%.1f'));
    end
    if cl == "pune", fprintf(fid, '\\midrule\n'); end
end
fprintf(fid, '\\bottomrule\n\\end{tabular}\n');
end

function s = capital(x), s = upper(extractBefore(x, 2)) + extractAfter(x, 1); end

function latex_E2(S, f, mlab, modes)
fid = fopen(f, 'w'); c = onCleanup(@() fclose(fid));
fprintf(fid, '%% generated by dcx_study_stats.m\n\\begin{tabular}{lllrrr}\n\\toprule\n');
fprintf(fid, 'Fault & Climate & Controller & Unplanned trips (rate) & Zone C/D exposure (min) & Energy (kWh)\\\\\n\\midrule\n');
for sc = ["chiller" "pump"]
    for cl = ["pune" "frankfurt"]
        for k = 1:3
            x = S.E2(S.E2.scenario == sc & S.E2.climate == cl & S.E2.mode == modes(k), :);
            if isempty(x), continue; end
            fprintf(fid, '%s & %s & %s & %d/%d {\\scriptsize[%.2f, %.2f]} & %s & %s\\\\\n', ...
                ternary(cl == "pune" && k == 1, capital(sc), ""), ternary(k == 1, capital(cl), ""), mlab(k), x.n_trip, x.n, x.trip_lo, x.trip_hi, ...
                pm(x.risk_min, x.risk_lo, x.risk_hi, '%.1f'), pm(x.energy_kwh, x.energy_lo, x.energy_hi, '%.1f'));
        end
    end
    if sc == "chiller", fprintf(fid, '\\midrule\n'); end
end
fprintf(fid, '\\bottomrule\n\\end{tabular}\n');
end

function latex_E3(S, f)
fid = fopen(f, 'w'); c = onCleanup(@() fclose(fid));
names = containers.Map({'haempc','ha_noHI','ha_noRUL','ha_noPrecool','empc'}, ...
    {'PI-HA-EMPC (full)','without Health Index','without RUL','without pre-cooling','EMPC (no health information)'});
fprintf(fid, '%% generated by dcx_study_stats.m\n\\begin{tabular}{lrrrr}\n\\toprule\n');
fprintf(fid, 'Variant & Unplanned trips & Zone C/D exposure (min) & Peak inlet (\\textdegree C) & Energy (kWh)\\\\\n\\midrule\n');
x = S.E3(S.E3.scenario == "all", :);
for i = 1:height(x)
    fprintf(fid, '%s & %d/%d {\\scriptsize[%.2f, %.2f]} & %s & %s & %s\\\\\n', names(char(x.variant(i))), x.n_trip(i), x.n(i), ...
        x.trip_lo(i), x.trip_hi(i), pm(x.risk_min(i), x.risk_lo(i), x.risk_hi(i), '%.1f'), pm(x.peak_c(i), x.peak_lo(i), x.peak_hi(i), '%.2f'), ...
        pm(x.energy_kwh(i), x.energy_lo(i), x.energy_hi(i), '%.1f'));
end
fprintf(fid, '\\bottomrule\n\\end{tabular}\n');
end

function latex_E4(S, f)
fid = fopen(f, 'w'); c = onCleanup(@() fclose(fid));
fprintf(fid, '%% generated by dcx_study_stats.m\n\\begin{tabular}{lrrrr}\n\\toprule\n');
fprintf(fid, 'Fault & RUL error & Unplanned-trip rate & Zone C/D exposure (min) & Pre-cooling (min)\\\\\n\\midrule\n');
for sc = ["chiller" "pump"]
    x = S.E4(S.E4.scenario == sc, :);
    for i = 1:height(x)
        fprintf(fid, '%s & %+.0f\\,\\%% & %.2f {\\scriptsize[%.2f, %.2f]} & %s & %s\\\\\n', ternary(i == 1, capital(sc), ""), x.rul_error_pct(i), ...
            x.trip_rate(i), x.trip_lo(i), x.trip_hi(i), pm(x.risk_min(i), x.risk_lo(i), x.risk_hi(i), '%.1f'), ...
            pm(x.precool_min(i), x.precool_lo(i), x.precool_hi(i), '%.0f'));
    end
    if sc == "chiller", fprintf(fid, '\\midrule\n'); end
end
fprintf(fid, '\\bottomrule\n\\end{tabular}\n');
end

function latex_E6(S, f)
fid = fopen(f, 'w'); c = onCleanup(@() fclose(fid));
fprintf(fid, '%% generated by dcx_study_stats.m\n\\begin{tabular}{lrrrr}\n\\toprule\n');
fprintf(fid, 'Controller & MPC solves & Mean (ms) & Median per-run p95 (ms) & Max (ms)\\\\\n\\midrule\n');
for i = 1:height(S.E6)
    fprintf(fid, '%s & %d & %.1f & %.1f & %.1f\\\\\n', strrep(S.E6.mode(i), '_', '\_'), S.E6.solves(i), S.E6.mean_ms(i), ...
        S.E6.median_run_p95_ms(i), S.E6.max_ms(i));
end
fprintf(fid, '\\bottomrule\n\\end{tabular}\n');
end

function figs_study(S, R, fdir, modes, mlab)
col = [0.45 0.45 0.45; 0.18 0.40 0.62; 0.80 0.33 0.10];
% --- Fig: E1 paired energy savings vs baseline per climate x workload
f = figure('Visible', 'off', 'Position', [100 100 900 360]);
E1 = R(R.experiment == "E1E2" & R.scenario == "normal", :);
cls = ["pune" "frankfurt"]; wls = ["diurnal" "flat" "bursty"];
for ci = 1:2
    subplot(1, 2, ci); hold on; grid on;
    for wi = 1:3
        for k = 2:3
            A = E1(E1.climate == cls(ci) & E1.workload == wls(wi) & E1.mode == modes(k), :);
            B = E1(E1.climate == cls(ci) & E1.workload == wls(wi) & E1.mode == "fixed", :);
            [~, ia, ib] = intersect(A.seed, B.seed);
            d = 100*(A.cooling_kwh(ia) - B.cooling_kwh(ib))./B.cooling_kwh(ib);
            [m, lo, hi] = tci(d); xpos = wi + (k - 2.5)*0.25;
            errorbar(xpos, m, m - lo, hi - m, 'o', 'Color', col(k, :), 'MarkerFaceColor', col(k, :), 'LineWidth', 1.2, ...
                'HandleVisibility', ternary(wi == 1, 'on', 'off'), 'DisplayName', mlab(k));
        end
    end
    set(gca, 'XTick', 1:3, 'XTickLabel', wls); xlim([0.5 3.5]); yline(0, 'k-', 'HandleVisibility', 'off');
    ylabel('cooling energy vs baseline (%)'); title(capital(cls(ci)));
    if ci == 1, legend('Location', 'southwest'); end
end
exportgraphics(f, fullfile(fdir, 'fig_E1_cooling_savings.pdf')); exportgraphics(f, fullfile(fdir, 'fig_E1_cooling_savings.png'), 'Resolution', 200); close(f);
% --- Fig: E2/E3 trip rates
f = figure('Visible', 'off', 'Position', [100 100 900 340]);
x = S.E3(S.E3.scenario == "all", :);
lbl = ["Full" "no HI" "no RUL" "no pre-cool" "EMPC"]; [~, ord] = ismember(["haempc" "ha_noHI" "ha_noRUL" "ha_noPrecool" "empc"], x.variant);
ord = ord(ord > 0);
subplot(1, 2, 1); hold on; grid on;
b = bar(1:numel(ord), x.trip_rate(ord), 0.6, 'FaceColor', [0.75 0.75 0.75]);
errorbar(1:numel(ord), x.trip_rate(ord), x.trip_rate(ord) - x.trip_lo(ord), x.trip_hi(ord) - x.trip_rate(ord), 'k.', 'LineWidth', 1);
set(gca, 'XTick', 1:numel(ord), 'XTickLabel', lbl(1:numel(ord))); ylabel('unplanned-trip rate'); ylim([0 1]); title('E3 ablation (fault runs)');
subplot(1, 2, 2); hold on; grid on;
for sc = ["chiller" "pump"]
    y = S.E4(S.E4.scenario == sc, :);
    errorbar(y.rul_error_pct, y.trip_rate, y.trip_rate - y.trip_lo, y.trip_hi - y.trip_rate, '-o', 'LineWidth', 1.2, 'DisplayName', sc);
end
xlabel('RUL estimation error (%)  (+ = optimistic)'); ylabel('unplanned-trip rate'); ylim([0 1]); legend('Location', 'northwest'); title('E4 RUL-error sensitivity');
exportgraphics(f, fullfile(fdir, 'fig_E3E4_risk.pdf')); exportgraphics(f, fullfile(fdir, 'fig_E3E4_risk.png'), 'Resolution', 200); close(f);
% --- Fig: E6 solve-time distribution
f = figure('Visible', 'off', 'Position', [100 100 450 300]);
m = R(R.mode ~= "fixed", :); boxchart(categorical(m.mode), m.solve_ms_p95); ylabel('per-run p95 mpcmove time (ms)'); grid on;
exportgraphics(f, fullfile(fdir, 'fig_E6_solve.pdf')); close(f);
end

function o = ternary(c, a, b), if c, o = a; else, o = b; end, end
