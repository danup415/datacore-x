function R = dcx_train_models(opts)
%DCX_TRAIN_MODELS Train and evaluate asset-specific diagnosis models (item 6).
%   For pump, CRAH fan and cooling-plant domains:
%     * bagged-tree classifiers on SENSOR-ONLY vs SENSOR + PHYSICS-RESIDUAL
%       features (research question: does physics-informed fusion help?)
%     * the rule-based physics-residual estimator v0 as baseline
%     * Isolation-Forest anomaly detector trained on healthy windows only
%   Train/test split is BY RUN (70/30, stratified by fault kind).
arguments
    opts.Seed (1,1) double = 7
    opts.TrainFrac (1,1) double = 0.7
end
here = fileparts(mfilename('fullpath'));
S = load(fullfile(here, 'data', 'dataset.mat')); D = S.D;
rng(opts.Seed);
% run-level split, stratified by kind
test = false(height(D.runs), 1);
kinds = unique(D.runs.kind);
for k = 1:numel(kinds)
    r = find(strcmp(D.runs.kind, kinds{k}) );
    r = r(randperm(numel(r)));
    test(r(1:round((1 - opts.TrainFrac)*numel(r)))) = true;
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
mdir = fullfile(here, 'models'); if ~isfolder(mdir), mkdir(mdir); end
rows = {};
for dn = fieldnames(spec)'
    d = dn{1}; sp = spec.(d); tb = D.(d);
    sv = tb{:, sp.sev}; [mx, ai] = max(sv, [], 2);
    y = repmat({'Healthy'}, height(tb), 1);
    y(mx >= 0.15) = sp.cls(ai(mx >= 0.15));
    keep = mx == 0 | mx >= 0.15;
    tb = tb(keep, :); y = categorical(y(keep));
    isTest = ismember(tb.run, testRuns);
    sets = {'sensor-only', sp.raw; 'sensor+physics', [sp.raw sp.phys]};
    for s = 1:2
        X = tb{:, sets{s,2}};
        mdl = fitcensemble(X(~isTest,:), y(~isTest), 'Method', 'Bag', 'NumLearningCycles', 150, ...
            'Learners', templateTree('MinLeafSize', 3, 'Reproducible', true));
        yp = predict(mdl, X(isTest,:));
        [f1, acc, rec] = scores(y(isTest), yp);
        rows(end+1,:) = {d, sets{s,1}, f1, acc, rec, sum(~isTest), sum(isTest)}; %#ok<AGROW>
        if s == 2
            ClassNames = mdl.ClassNames; Features = sets{s,2}; %#ok<NASGU>
            model = compact(mdl); save(fullfile(mdir, ['dcx_' d '_classifier.mat']), 'model', 'Features', 'ClassNames');
            R.(d).confusion = confusionmat(y(isTest), yp, 'Order', mdl.ClassNames);
            R.(d).classes = mdl.ClassNames;
            imp = predictorImportance(mdl); R.(d).importance = table(Features(:), imp(:), 'VariableNames', {'feature','importance'});
            R.(d).detection = detectionDelay(tb(isTest,:), yp, D.runs);
        end
    end
    % rule-based physics-residual baseline (estimator v0 thresholds)
    yr = ruleBaseline(d, tb(isTest,:), sp.cls);
    [f1, acc, rec] = scores(y(isTest), yr);
    rows(end+1,:) = {d, 'rule baseline v0', f1, acc, rec, 0, sum(isTest)}; %#ok<AGROW>
    % anomaly detection: Isolation Forest on healthy training windows (physics features)
    Xa = tb{:, [sp.raw sp.phys]};
    h = (~isTest) & y == 'Healthy';
    [forest, ~, sc] = iforest(Xa(h,:), 'ContaminationFraction', 0.01, 'NumLearners', 200);
    [isAn, ~] = isanomaly(forest, Xa(isTest,:));
    yt = y(isTest) ~= 'Healthy';
    rows(end+1,:) = {d, 'anomaly (iForest)', NaN, mean(isAn == yt), [mean(isAn(yt)) 1 - mean(isAn(~yt))], sum(h), sum(isTest)}; %#ok<AGROW>
    save(fullfile(mdir, ['dcx_' d '_iforest.mat']), 'forest');
end
R.summary = cell2table(rows, 'VariableNames', {'domain','model','macroF1','accuracy','recall_or_[recall,specificity]','n_train','n_test'});
R.split = struct('test_runs', testRuns, 'note', 'split by run, stratified by fault kind');
save(fullfile(here, 'models', 'dcx_pdm_results.mat'), 'R');
disp(R.summary);
end

% -------------------------------------------------------------------------
function [f1, acc, rec] = scores(yt, yp)
c = categories(yt); f = zeros(numel(c),1); rec = zeros(1, numel(c));
for i = 1:numel(c)
    tp = sum(yt == c{i} & yp == c{i}); fp = sum(yt ~= c{i} & yp == c{i}); fn = sum(yt == c{i} & yp ~= c{i});
    p = tp/max(tp+fp,1); r = tp/max(tp+fn,1); f(i) = 2*p*r/max(p+r, eps); rec(i) = r;
end
f1 = mean(f); acc = mean(yt == yp);
end

function y = ruleBaseline(d, tb, cls)
n = height(tb); y = repmat({'Healthy'}, n, 1);
for i = 1:n
    switch d
        case 'pump'
            sv = max(0, tb.r_vib(i))/7.1; sh = 2.5*max(0, tb.r_head(i)); se = 2*max(0, tb.r_eff(i));
            if max([sv sh se]) < 0.10, continue; end
            if sh >= 0.12 && sv > 0.15, y{i} = cls{2};
            elseif sv > 0.10 && sh < 0.12, y{i} = cls{1};
            else, y{i} = cls{3}; end
        case 'crah'
            rv = max(0, tb.r_vib(i))/4.5; rp = max(0, tb.r_power(i)); ra = max(0, tb.r_airflow(i));
            if max([rv 1.6*ra 1.2*rp*(rv < 0.08)]) < 0.10, continue; end
            if ra > 0.08 && rv < 0.1, y{i} = cls{3}; elseif rp > 0.08, y{i} = cls{2}; else, y{i} = cls{1}; end
        case 'plant'
            s = [2.2*max(0, tb.r_cop(i)), 1.4*max(0, tb.r_hx(i))/0.72, 0.6*max(0, max(tb.r_ct1(i), tb.r_ct2(i)))];
            [m, k] = max(s); if m >= 0.12, y{i} = cls{k}; end
    end
end
y = categorical(y);
end

function T = detectionDelay(tb, yp, runs)
% first time two consecutive windows of a faulty test run are classified as the true class
ids = unique(tb.run); rows = {};
for r = ids'
    ri = runs(runs.run == r, :);
    if strcmp(ri.kind{1}, 'healthy'), continue; end
    m = tb.run == r; t = tb.t(m); p = yp(m);
    sev = max(tb{m, startsWith(tb.Properties.VariableNames, 'sev_')}, [], 2);
    hit = find(p(1:end-1) ~= 'Healthy' & p(2:end) ~= 'Healthy', 1);
    if isempty(hit), rows(end+1,:) = {r, ri.kind{1}, NaN, NaN}; %#ok<AGROW>
    else, rows(end+1,:) = {r, ri.kind{1}, t(hit) - ri.onset_s, sev(hit)}; end %#ok<AGROW>
end
T = cell2table(rows, 'VariableNames', {'run','kind','detect_after_onset_s','severity_at_detection'});
end
