function E = dcx_e5_ci(opts)
%DCX_E5_CI Experiment E5 with confidence intervals: diagnosis macro-F1 and
%   pump-bearing RUL error, using CLUSTER (run-level) bootstrap 95 % CIs,
%   because windows from the same run are correlated.
%   Reproduces the deterministic split and models of dcx_train_models
%   (seed 7, 70/30 by run, bagged trees 150 cycles) and dcx_rul.
%   Writes pdm/models/dcx_e5_ci.mat and control/results/study/tables/{E5_*.csv, tab_E5.tex}.
arguments
    opts.B (1,1) double = 2000
    opts.Seed (1,1) double = 7
end
here = fileparts(mfilename('fullpath')); root = fileparts(here);
S = load(fullfile(root, 'pdm', 'data', 'dataset.mat')); D = S.D;
rng(opts.Seed);
test = false(height(D.runs), 1); kinds = unique(D.runs.kind);
for k = 1:numel(kinds)
    r = find(strcmp(D.runs.kind, kinds{k})); r = r(randperm(numel(r)));
    test(r(1:round(0.3*numel(r)))) = true;
end
testRuns = D.runs.run(test);
spec = struct( ...
  'pump',  struct('sev', {{'sev_brg','sev_cav','sev_eff'}}, 'cls', {{'F01_bearing','F02_cavitation','PUMP_EFF'}}, ...
                  'raw', {{'speed','flow','head','power','eff','vib','vib_sd','current'}}, 'phys', {{'r_head','r_eff','r_vib'}}), ...
  'crah',  struct('sev', {{'sev_imb','sev_brg','sev_block'}}, 'cls', {{'F03_imbalance','F04_bearing','BLOCKAGE'}}, ...
                  'raw', {{'speed','airflow','fan_kw','vib','vib_sd','supply','valve'}}, 'phys', {{'r_vib','r_power','r_airflow'}}), ...
  'plant', struct('sev', {{'sev_ch','sev_hx','sev_ct'}}, 'cls', {{'F06_chiller','F05_hx_fouling','F07_tower'}}, ...
                  'raw', {{'ch_load','cop','plr','cwe','chws','hx_duty','hx_eff','app1','app2','ct1_fan','ct2_fan','ch_power'}}, ...
                  'phys', {{'r_cop','r_hx','r_ct1','r_ct2'}}));
rows = {}; E = struct();
for dn = fieldnames(spec)'
    d = dn{1}; sp = spec.(d); tb = D.(d);
    sv = tb{:, sp.sev}; [mx, ai] = max(sv, [], 2);
    y = repmat({'Healthy'}, height(tb), 1); y(mx >= 0.15) = sp.cls(ai(mx >= 0.15));
    keep = mx == 0 | mx >= 0.15; tb = tb(keep, :); y = categorical(y(keep));
    isTest = ismember(tb.run, testRuns); runId = tb.run(isTest);
    sets = {'sensor-only', sp.raw; 'sensor+physics', [sp.raw sp.phys]};
    for s = 1:2
        X = tb{:, sets{s, 2}};
        mdl = fitcensemble(X(~isTest, :), y(~isTest), 'Method', 'Bag', 'NumLearningCycles', 150, ...
            'Learners', templateTree('MinLeafSize', 3, 'Reproducible', true));
        yt = y(isTest); yp = predict(mdl, X(isTest, :));
        f1 = macroF1(yt, yp);
        [lo, hi] = clusterBoot(@(i) macroF1(yt(i), yp(i)), runId, opts.B);
        rows(end+1, :) = {d, sets{s, 1}, f1, lo, hi, numel(unique(runId)), sum(isTest)}; %#ok<AGROW>
        E.(d).(matlab.lang.makeValidName(sets{s, 1})) = struct('yt', yt, 'yp', yp, 'run', runId);
    end
end
E.diag = cell2table(rows, 'VariableNames', {'domain','features','macroF1','ci_lo','ci_hi','test_runs','test_windows'});
disp(E.diag)
% ---------------- RUL: prediction-level errors tagged by test run
R = load(fullfile(root, 'pdm', 'data', 'dataset.mat')); runs = R.D.rul; runs = runs(~isnan([runs.t_fail]));
tr = runs(1:12); te = runs(13:end); thr = 5.45;
toTab = @(r) table(r.t, max(r.hi, 0) + 0.05, 'VariableNames', {'Time','HI'});
trainData = arrayfun(toTab, tr, 'UniformOutput', false);
mk = {@() exponentialDegradationModel('LifeTimeUnit', "hours"), @() linearDegradationModel('LifeTimeUnit', "hours")};
names = {'exponential', 'linear'}; rrows = {};
for m = 1:2
    err = []; cover = []; rid = []; frac = [];
    for k = 1:numel(te)
        r = te(k); d = toTab(r); det = find(d.HI > 0.35, 1); if isempty(det), continue; end
        mdl = mk{m}(); fit(mdl, trainData, "Time", "HI");
        for i = det:numel(d.Time)
            update(mdl, d(i, :));
            if mod(i - det, 5) ~= 0 || d.Time(i) >= r.t_fail, continue; end
            [est, ci] = predictRUL(mdl, thr); est = hours(est); ci = hours(ci); truth = r.t_fail - d.Time(i);
            err(end+1) = (est - truth)*60; cover(end+1) = truth >= ci(1) && truth <= ci(2); rid(end+1) = k; %#ok<AGROW>
            frac(end+1) = (d.Time(i) - d.Time(det))/max(r.t_fail - d.Time(det), eps); %#ok<AGROW>
        end
    end
    rm = @(i) sqrt(mean(err(i).^2));
    [lo, hi] = clusterBoot(rm, rid(:), opts.B);
    late = find(frac > 0.5); [llo, lhi] = clusterBoot(@(i) sqrt(mean(err(late(i)).^2)), rid(late)', opts.B);
    perrun = arrayfun(@(k) sqrt(mean(err(rid == k).^2)), unique(rid));
    rrows(end+1, :) = {names{m}, rm(1:numel(err)), lo, hi, sqrt(mean(err(late).^2)), llo, lhi, mean(cover), ...
        min(perrun), max(perrun), numel(unique(rid)), numel(err)}; %#ok<AGROW>
end
E.rul = cell2table(rrows, 'VariableNames', {'model','RMSE_min','ci_lo','ci_hi','RMSE_late_min','late_lo','late_hi', ...
    'CI90_coverage','perrun_min','perrun_max','test_runs','predictions'});
disp(E.rul)
save(fullfile(root, 'pdm', 'models', 'dcx_e5_ci.mat'), 'E');
tdir = fullfile(here, 'results', 'study', 'tables'); if ~isfolder(tdir), mkdir(tdir); end
writetable(E.diag, fullfile(tdir, 'E5_diagnosis.csv')); writetable(E.rul, fullfile(tdir, 'E5_rul.csv'));
fid = fopen(fullfile(tdir, 'tab_E5.tex'), 'w');
fprintf(fid, '%% generated by dcx_e5_ci.m\n\\begin{tabular}{lrr}\n\\toprule\nAsset class & Sensor-only macro-F1 & Sensor + physics-residual macro-F1\\\\\n\\midrule\n');
lab = containers.Map({'pump','crah','plant'}, {'CHW pumps','CRAH fans','Chiller / HX / towers'});
for d = ["pump" "crah" "plant"]
    a = E.diag(E.diag.domain == d & E.diag.features == "sensor-only", :); b = E.diag(E.diag.domain == d & E.diag.features == "sensor+physics", :);
    fprintf(fid, '%s & %.3f {\\scriptsize[%.3f, %.3f]} & %.3f {\\scriptsize[%.3f, %.3f]}\\\\\n', lab(char(d)), a.macroF1, a.ci_lo, a.ci_hi, b.macroF1, b.ci_lo, b.ci_hi);
end
fprintf(fid, '\\bottomrule\n\\end{tabular}\n'); fclose(fid);
end

function f1 = macroF1(yt, yp)
c = categories(yt); f = nan(numel(c), 1);
for i = 1:numel(c)
    tp = sum(yt == c{i} & yp == c{i}); fp = sum(yt ~= c{i} & yp == c{i}); fn = sum(yt == c{i} & yp ~= c{i});
    if tp + fn == 0, continue; end                      % class absent from this resample
    p = tp/max(tp + fp, 1); r = tp/max(tp + fn, 1); f(i) = 2*p*r/max(p + r, eps);
end
f1 = mean(f, 'omitnan');
end

function [lo, hi] = clusterBoot(stat, cluster, B)
u = unique(cluster); n = numel(u); v = zeros(B, 1);
idx = cell(n, 1); for j = 1:n, idx{j} = find(cluster == u(j)); end
for b = 1:B
    pick = u(randi(n, n, 1)); ii = [];
    for j = 1:n, ii = [ii; idx{find(u == pick(j), 1)}]; end %#ok<AGROW>
    v(b) = stat(ii);
end
q = prctile(v, [2.5 97.5]); lo = q(1); hi = q(2);
end
