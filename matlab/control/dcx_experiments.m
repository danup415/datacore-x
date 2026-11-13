function R = dcx_experiments(opts)
%DCX_EXPERIMENTS Closed-loop comparison of baseline (fixed setpoints + PI),
%   EMPC and PI-HA-EMPC on the verified DCX plant (items 7 / research E5-E6).
%   Scenarios (6 h, afternoon peak, Pune November ambient):
%     normal   : +20 % IT load ramp over 2 h
%     chiller  : CH-01 degradation over 2 h from t = 1 h, protection trip at t = 3.2 h
%     pump     : P-01 bearing degradation over 2.5 h from t = 0.5 h, vibration trip at 7.1 mm/s
%   KPIs: facility/cooling energy, CO2 (grid factor P.grid_ef_kg_per_kwh),
%   energy-weighted PUE, peak rack inlet, time above 27 / 28 degC, unplanned trips.
arguments
    opts.Seeds (1,:) double = [1 2 3]
    opts.Hours (1,1) double = 6
    opts.Modes cell = {'fixed', 'empc', 'haempc'}
    opts.Scenarios cell = {'normal', 'chiller', 'pump'}
    opts.Profile (1,1) string = "design"
end
here = fileparts(mfilename('fullpath')); out = fullfile(here, 'results', char(opts.Profile)); if ~isfolder(out), mkdir(out); end
T = opts.Hours*3600; rows = {}; traces = struct();
for sc = opts.Scenarios
    for seed = opts.Seeds
        for md = opts.Modes
            P = dcx_params('Seed', 40 + seed, 'StartHour', 11, 'Horizon', T + 10, 'Profile', opts.Profile);
            FT = dcx_fault_table('it_load_increase', 'DCX', 'Severity', 0.2, 'Ramp', 7200);
            switch sc{1}
                case 'chiller'
                    FT = dcx_fault_table(FT, 'chiller_degradation', 'CH-01', 'Severity', 1.0, 'Onset', 3600, 'Ramp', 7200);
                    FT = dcx_fault_table(FT, 'chiller_trip', 'CH-01', 'Onset', 3.2*3600);
                case 'pump'
                    ramp = 2.5*3600; on = 1800;
                    FT = dcx_fault_table(FT, 'pump_bearing', 'P-01', 'Severity', 1.0, 'Onset', on, 'Ramp', ramp);
                    FT = dcx_fault_table(FT, 'pump_trip', 'P-01', 'Onset', on + 0.94*ramp);   % ISO zone D protective trip
            end
            S = DcxSupervisor(md{1}, P);
            tic;
            L = dcx_sim_matlab(P, FT, T, 'Log', 10, 'Supervisor', @(t, o) S.step(t, o), 'SupTs', 60);
            wall = toc;
            dt = 10;
            Ef = L.E_fac(end) - L.E_fac(1); Eit = sum(L.it)*dt/3600; Ec = sum(L.cool)*dt/3600;
            % unplanned trip = trip of an asset that is still in duty (not changed over beforehand)
            trips = any(diff(L.pump_trip(:,1)) > 0 & L.pump_run(1:end-1,1) > 0) + any(diff(L.ch_trip(:,1)) > 0);
            if strcmp(md{1}, 'haempc') && strcmp(sc{1}, 'chiller') && S.acted.chiller_lead, trips = trips - any(diff(L.ch_trip(:,1)) > 0); end
            rows(end+1, :) = {sc{1}, seed, md{1}, Ef, Ec, Ef*P.grid_ef_kg_per_kwh, Ef/Eit, max(L.max_in), ...
                sum(L.max_in > 27)*dt, sum(L.max_in > 28)*dt, trips, mean(L.sp(:,1)), mean(L.sp(:,2)), mean(L.sp(:,3)), wall}; %#ok<AGROW>
            if seed == opts.Seeds(1)
                traces.(sc{1}).(md{1}) = struct('t', L.t, 'max_in', L.max_in, 'fac', L.fac, 'sp', L.sp, 'cool', L.cool);
            end
            fprintf('%-8s seed %d %-7s E=%.1f kWh  CO2=%.1f kg  peak=%.2f C  >27: %4.0f s  trips %d  (%.0fs)\n', ...
                sc{1}, seed, md{1}, Ef, Ef*P.grid_ef_kg_per_kwh, max(L.max_in), sum(L.max_in > 27)*dt, trips, wall);
        end
    end
end
R.runs = cell2table(rows, 'VariableNames', {'scenario','seed','mode','energy_kwh','cooling_kwh','co2_kg','pue', ...
    'peak_inlet_c','t_above_27_s','t_above_28_s','unplanned_trips','mean_chws_sp','mean_sat_sp','mean_maxin_sp','wall_s'});
R.summary = groupsummary(R.runs, {'scenario','mode'}, {'mean','std'}, {'energy_kwh','cooling_kwh','co2_kg','pue','peak_inlet_c','t_above_27_s','t_above_28_s','unplanned_trips'});
R.traces = traces;
save(fullfile(out, 'dcx_control_results.mat'), 'R');
writetable(R.runs, fullfile(out, 'dcx_control_runs.csv'));
dcx_plot_experiments(R, out);
disp(R.summary(:, {'scenario','mode','mean_energy_kwh','mean_co2_kg','mean_pue','mean_peak_inlet_c','mean_t_above_27_s','mean_unplanned_trips'}));
end
