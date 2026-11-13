function T = dcx_study(opts)
%DCX_STUDY Research study for the PI-HA-EMPC paper (experiments E1-E4, E6).
%   Runs the closed-loop plan from dcx_study_plan in parallel (parfeval) and
%   appends one row per run to control/results/study/runs.csv as each run
%   completes (resumable: runs already in the CSV are skipped).
%     E1  energy / thermal performance  : climates x workloads x seeds, normal scenario
%     E2  fault scenarios (risk)        : chiller and pump degradation -> trip
%     E3  ablations                     : ha_noHI, ha_noRUL, ha_noPrecool
%     E4  RUL-error sensitivity         : RUL estimate scaled by 0.5 ... 2.0
%     E6  computational cost            : mpcmove wall time per step (all MPC runs)
%   T = dcx_study('Plan',"full")    T = dcx_study('Plan',"smoke")
%   Run from a separate MATLAB with  matlab -batch "dcx_startup; dcx_study"
arguments
    opts.Plan (1,1) string = "full"
    opts.Workers (1,1) double = 10
end
here = fileparts(mfilename('fullpath')); root = fileparts(here);
out = fullfile(here, 'results', 'study'); if ~isfolder(out), mkdir(out); end
csv = fullfile(out, sprintf('runs_%s.csv', opts.Plan));
specs = dcx_study_plan(opts.Plan);
done = strings(0, 1);
if isfile(csv)
    D = readtable(csv, 'TextType', 'string'); done = D.key;
end
todo = specs(~ismember(specs.key, done), :);
fprintf('[study] plan %s: %d runs, %d already done, %d to run\n', opts.Plan, height(specs), height(specs) - height(todo), height(todo));
if isempty(todo), T = readtable(csv, 'TextType', 'string'); return; end
if opts.Workers == 0
    % serial, in-process (low-memory machines); each run appended as it completes
    t0 = tic;
    for k = 1:height(todo)
        try
            r = dcx_study_run(table2struct(todo(k, :)));
        catch err
            fprintf(2, '[study] %s failed: %s\n', todo.key(k), err.message); continue
        end
        row = struct2table(r);
        if isfile(csv), writetable(row, csv, 'WriteMode', 'append'); else, writetable(row, csv); end
        el = toc(t0);
        fid = fopen(fullfile(out, sprintf('progress_%s.txt', opts.Plan)), 'w');
        fprintf(fid, '%d/%d done, %.1f min elapsed, eta %.0f min, last %s\n', k, height(todo), el/60, el/k*(height(todo) - k)/60, r.key); fclose(fid);
    end
    T = readtable(csv, 'TextType', 'string'); return
end
pool = gcp('nocreate');
if isempty(pool), pool = parpool('Processes', opts.Workers); end
parfevalOnAll(pool, @addpath, 0, genpath(root));
F(height(todo)) = parallel.FevalFuture;
for i = 1:height(todo)
    F(i) = parfeval(pool, @dcx_study_run, 1, table2struct(todo(i, :)));
end
t0 = tic;
for k = 1:height(todo)
    try
        [~, r] = fetchNext(F);
    catch err
        fprintf(2, '[study] run failed: %s\n', err.message); continue
    end
    row = struct2table(r);
    if isfile(csv), writetable(row, csv, 'WriteMode', 'append'); else, writetable(row, csv); end
    el = toc(t0);
    fprintf('[study] %4d/%d  %-46s E=%6.1f kWh  >28C %5.0f s  trips %d  solve %.0f ms  (eta %.0f min)\n', k, height(todo), ...
        r.key, r.energy_kwh, r.t_above_28_s, r.unplanned_trips, r.solve_ms_mean, el/k*(height(todo) - k)/60);
end
T = readtable(csv, 'TextType', 'string');
end
