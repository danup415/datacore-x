function run_all(opts)
%RUN_ALL Reproduce every result of the PI-HA-EMPC paper from scratch.
%   run_all                       full pipeline (about 5 h serial on an 8 GB laptop)
%   run_all('Stage',"stats")      only recompute statistics/tables/macros from runs_full.csv
%   run_all('Workers',4)          parallel process workers (needs ~1 GB RAM per worker)
%   Stages (in order): calibrate -> verify -> pdm -> ident -> study -> credibility -> stats -> paper
%   Configuration and seeds: config/study_config.json (frozen for release v1.0.0).
arguments
    opts.Stage (1,1) string = "all"
    opts.Workers (1,1) double = 0      % 0 = serial in-process (8 GB machines); >0 = parallel process workers
end
root = fileparts(mfilename('fullpath')); cd(root); addpath(genpath(root));
cfg = jsondecode(fileread(fullfile(root, 'config', 'study_config.json')));
st = @(s) opts.Stage == "all" || opts.Stage == s;
t0 = tic;
if st("calibrate")
    dcx_calibrate('Year', cfg.weather_year);                       % chiller/tower/pumps/CRAH/grid + Pune weather
    for s = string(cfg.climates(:))', dcx_weather(s, 'Year', cfg.weather_year); end
    dcx_validate_hydraulics('Profile', "design"); dcx_validate_hydraulics('Profile', "calibrated");
end
if st("verify")
    R = dcx_xverify(); assert(all(R.pass), 'MATLAB stepper cross-verification failed');
    dcx_build_model(); R = dcx_xverify(@(P,FT,T) dcx_run_model(P,FT,T)); assert(all(R.pass), 'Simulink cross-verification failed');
    A = dcx_test_ats_chart(); assert(A.pass, 'Stateflow ATS test failed');
end
if st("pdm")
    dcx_gen_dataset(); dcx_train_models(); dcx_rul();
end
if st("ident")
    for s = string(cfg.climates(:))'
        dcx_ident('Profile', "calibrated", 'Climate', s, 'Hours', cfg.ident_hours, 'Days', cfg.ident_days(:)', ...
            'Method', "auto", 'Orders', cfg.ident_orders(:)', 'Seed', cfg.ident_seed);
    end
end
if st("study"), dcx_study('Plan', "paper", 'Workers', opts.Workers); end
if st("credibility"), dcx_credibility(); end
if st("stats"), dcx_study_stats('Plan', "paper"); end
if st("paper") || st("stats"), dcx_paper_macros('Plan', "paper"); end
fprintf('[run_all] stage %s finished in %.1f h\n', opts.Stage, toc(t0)/3600);
end
