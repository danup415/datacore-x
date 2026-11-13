function R = dcx_rul(opts)
%DCX_RUL Remaining-useful-life estimation for CHW pump bearings (item 6).
%   Health indicator: vibration residual (measured RMS minus speed-dependent
%   healthy baseline), failure = ISO 10816 zone C/D boundary (7.1 mm/s).
%   Compares Predictive Maintenance Toolbox exponential and linear
%   degradation models; RUL reported with 90 % confidence bounds and scored
%   against simulated ground truth on held-out run-to-failure runs.
arguments
    opts.TrainRuns (1,1) double = 12
    opts.Threshold (1,1) double = 5.45     % residual mm/s at ~76 % speed (7.1 - 1.65)
end
here = fileparts(mfilename('fullpath'));
S = load(fullfile(here, 'data', 'dataset.mat')); runs = S.D.rul;
runs = runs(~isnan([runs.t_fail]));
tr = runs(1:opts.TrainRuns); te = runs(opts.TrainRuns+1:end);
toTab = @(r) table(r.t, max(r.hi, 0) + 0.05, 'VariableNames', {'Time','HI'});
trainData = arrayfun(toTab, tr, 'UniformOutput', false);
mk = {@() exponentialDegradationModel('LifeTimeUnit', "hours"), @() linearDegradationModel('LifeTimeUnit', "hours")};
names = {'exponential', 'linear'};
rows = {}; curves = struct();
for m = 1:2
    err = []; cover = []; frac = []; curves.(names{m}) = zeros(0, 5);
    for k = 1:numel(te)
        r = te(k); d = toTab(r);
        det = find(d.HI > 0.35, 1);                     % start prognosis after detection
        if isempty(det), continue; end
        mdl = mk{m}(); fit(mdl, trainData, "Time", "HI");
        for i = det:numel(d.Time)
            update(mdl, d(i, :));
            if mod(i - det, 5) ~= 0 || d.Time(i) >= r.t_fail, continue; end
            [est, ci] = predictRUL(mdl, opts.Threshold);
            est = hours(est); ci = hours(ci); truth = r.t_fail - d.Time(i);
            err(end+1) = est - truth; cover(end+1) = truth >= ci(1) && truth <= ci(2); %#ok<AGROW>
            frac(end+1) = (d.Time(i) - d.Time(det))/max(r.t_fail - d.Time(det), eps); %#ok<AGROW>
            if k == 1, curves.(names{m})(end+1, :) = [d.Time(i), truth, est, ci(:)']; end
        end
    end
    late = frac > 0.5;
    rows(end+1, :) = {names{m}, sqrt(mean(err.^2))*60, mean(abs(err))*60, sqrt(mean(err(late).^2))*60, mean(cover), numel(err)}; %#ok<AGROW>
end
R.summary = cell2table(rows, 'VariableNames', {'model','RMSE_min','MAE_min','RMSE_late_half_min','CI90_coverage','n_predictions'});
R.curves = curves; R.threshold = opts.Threshold; R.note = 'RUL in time-compressed simulation hours; ground truth from noise-free vibration crossing 7.1 mm/s';
save(fullfile(here, 'models', 'dcx_rul_results.mat'), 'R');
disp(R.summary);
end
