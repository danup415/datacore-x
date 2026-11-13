function D = dcx_gen_dataset(opts)
%DCX_GEN_DATASET Labelled fault dataset from the verified DCX plant (item 5).
%   Each run varies seed (utilisation noise), time of day, IT load, operating
%   setpoints and fault parameters (asset, severity, onset, ramp). Splits are
%   made by RUN, never by window (blueprint §4.3). Saves pdm/data/dataset.mat.
arguments
    opts.RunsPerClass (1,1) double = 10
    opts.T (1,1) double = 2700
    opts.RulRuns (1,1) double = 16
    opts.Seed (1,1) double = 2026
end
here = fileparts(mfilename('fullpath')); out = fullfile(here, 'data'); if ~isfolder(out), mkdir(out); end
rng(opts.Seed);
domains = {'pump', {'healthy','pump_bearing','pump_cavitation','pump_efficiency'}; ...
           'crah', {'healthy','fan_imbalance','fan_bearing','crah_filter_blockage'}; ...
           'plant', {'healthy','chiller_degradation','hx_fouling','tower_degradation'}};
runs = {}; tabs = struct('pump', [], 'crah', [], 'plant', []);
rid = 0; t0 = tic;
for d = 1:size(domains,1)
    for c = 1:numel(domains{d,2})
        for r = 1:opts.RunsPerClass
            rid = rid + 1;
            kind = domains{d,2}{c};
            seed = 100 + rid; hour = 24*rand;
            P = dcx_params('Seed', seed, 'StartHour', hour, 'Horizon', opts.T + 10);
            P.sp.dp_kpa = 160 + 40*rand; P.sp.supply_air_c = 20.5 + 2*rand; P.sp.chws_c = 16.5 + 2.5*rand;
            FT = zeros(32,9);
            if rand < 0.5, FT = dcx_fault_table(FT, 'it_load_increase', 'DCX', 'Severity', 0.3*rand); end
            sev = 0.4 + 0.6*rand; on = 300 + 600*rand; ramp = 600 + 1200*rand; asset = '';
            switch kind
                case 'pump_bearing',      asset = sprintf('P-%02d', randi(2)); FT = dcx_fault_table(FT, kind, asset, 'Severity', sev, 'Onset', on, 'Ramp', ramp);
                case 'pump_cavitation',   asset = sprintf('P-%02d', randi(2)); FT = dcx_fault_table(FT, kind, asset, 'Severity', sev, 'Onset', on, 'Ramp', ramp);
                case 'pump_efficiency',   asset = sprintf('P-%02d', randi(2)); FT = dcx_fault_table(FT, kind, asset, 'Severity', 1, 'Onset', on, 'Ramp', ramp, 'P1', 0.4*sev);
                case 'fan_imbalance',     asset = sprintf('CRAH-%02d', randi(4)); FT = dcx_fault_table(FT, kind, asset, 'Severity', sev, 'Onset', on, 'Ramp', ramp);
                case 'fan_bearing',       asset = sprintf('CRAH-%02d', randi(4)); FT = dcx_fault_table(FT, kind, asset, 'Severity', sev, 'Onset', on, 'Ramp', ramp);
                case 'crah_filter_blockage', asset = sprintf('CRAH-%02d', randi(4)); FT = dcx_fault_table(FT, kind, asset, 'Severity', sev, 'Onset', on, 'Ramp', ramp);
                case 'chiller_degradation', asset = 'CH-01'; FT = dcx_fault_table(FT, kind, asset, 'Severity', sev, 'Onset', on, 'Ramp', ramp);
                case 'hx_fouling',        asset = 'HX-01'; FT = dcx_fault_table(FT, kind, asset, 'Severity', sev, 'Onset', on, 'Ramp', ramp);
                case 'tower_degradation', asset = sprintf('CT-%02d', randi(2)); FT = dcx_fault_table(FT, kind, asset, 'Severity', sev, 'Onset', on, 'Ramp', ramp);
            end
            L = dcx_sim_matlab(P, FT, opts.T, 'Sensors', true);
            Fx = dcx_features(L, P, P.sp);
            for dn = {'pump','crah','plant'}
                tb = Fx.(dn{1}); tb.run = repmat(rid, height(tb), 1);
                tabs.(dn{1}) = [tabs.(dn{1}); tb];
            end
            runs(end+1,:) = {rid, domains{d,1}, kind, asset, sev, on, ramp, seed, hour, P.sp.dp_kpa, P.sp.supply_air_c, P.sp.chws_c}; %#ok<AGROW>
            fprintf('run %3d %-6s %-22s %-8s sev %.2f  (%.0fs)\n', rid, domains{d,1}, kind, asset, sev, toc(t0));
        end
    end
end
D.runs = cell2table(runs, 'VariableNames', {'run','domain','kind','asset','severity','onset_s','ramp_s','seed','start_hour','dp_sp','sat_sp','chws_sp'});
D.pump = tabs.pump; D.crah = tabs.crah; D.plant = tabs.plant;

% ---------------- run-to-failure set for RUL (pump bearing, F01) -------------------
T = dcx_tag_list(); cv = find(strcmp(T.asset,'P-01') & strcmp(T.key,'vib_mms'));
cs = find(strcmp(T.asset,'P-01') & strcmp(T.key,'speed_pct'));
rul = struct('run', {}, 't', {}, 'hi', {}, 't_fail', {}, 'ramp', {});
for r = 1:opts.RulRuns
    on = 300 + 300*rand; ramp = 2400 + 2400*rand; Tr = ceil(on + ramp + 300);
    P = dcx_params('Seed', 500 + r, 'StartHour', 24*rand, 'Horizon', Tr + 10);
    FT = dcx_fault_table('pump_bearing', 'P-01', 'Severity', 1.0, 'Onset', on, 'Ramp', ramp);
    L = dcx_sim_matlab(P, FT, Tr, 'Sensors', true);
    n = floor(size(L.meas,1)/60);
    hi = zeros(n,1); tt = zeros(n,1);
    for k = 1:n
        ix = (k-1)*60 + (1:60); nn = mean(L.meas(ix,cs))/100;
        hi(k) = mean(L.meas(ix,cv)) - (0.9 + 1.3*nn^2);       % vibration residual (mm/s) = health indicator
        tt(k) = L.t(ix(end));
    end
    vtrue = L.truth(:, cv);
    tf = L.t(find(vtrue >= 7.1, 1));                          % ISO 10816 zone C/D boundary = failure
    if isempty(tf), tf = NaN; end
    rul(r) = struct('run', r, 't', tt/3600, 'hi', hi, 't_fail', tf/3600, 'ramp', ramp);
    fprintf('RUL run %2d  ramp %.0fs  failure at %.0fs\n', r, ramp, tf);
end
D.rul = rul;
D.meta = struct('generated', datetime('now'), 'generator', 'dcx_gen_dataset', 'plant', 'dcx_sim_matlab (verified vs DCX_Facility, 42/42)', ...
    'window_s', 120, 'hop_s', 60, 'label_rule', 'class = argmax severity if >= 0.15; healthy if 0; excluded if (0, 0.15)');
save(fullfile(out, 'dataset.mat'), 'D', '-v7.3');
fprintf('dataset saved: %d runs, %d pump / %d crah / %d plant windows, %d RUL runs (%.0f s)\n', ...
    height(D.runs), height(D.pump), height(D.crah), height(D.plant), numel(rul), toc(t0));
end
