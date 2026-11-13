function S = dcx_study_plan(plan)
%DCX_STUDY_PLAN Experiment design table for dcx_study.
%   Each seed k selects the IT-utilisation noise realisation AND the start
%   day 15 + 36(k-1) (10 days spread over the year), so seeds also sample
%   seasonal weather. All runs: calibrated profile, 6 h from 11:00.
arguments
    plan (1,1) string = "full"
end
seeds = 1:10;
if plan == "ablation2"
    % E3b: component ablations (MPC-side health vs discrete actions) + 'ha_none' sanity check
    rows = {};
    for cl = ["pune" "frankfurt"], for sc = ["chiller" "pump"], for sd = seeds, for md = ["ha_noActions" "ha_actionsOnly"]
        rows(end+1, :) = {"E3b", cl, "diurnal", sc, sd, md, 1.0}; %#ok<AGROW>
    end, end, end, end
    for sc = ["chiller" "pump"], for sd = 1:3
        rows(end+1, :) = {"E3b", "pune", "diurnal", sc, sd, "ha_none", 1.0}; %#ok<AGROW>
    end, end
    S = finish(rows); return
end
climates = ["pune" "frankfurt"]; workloads = ["diurnal" "flat" "bursty"];
if plan == "smoke"
    seeds = 1; climates = ["pune" "frankfurt"]; workloads = "diurnal";
end
rows = {};
add = @(exp, cl, wl, sc, sd, md, rs) {exp, cl, wl, sc, sd, md, rs};
% E1 + E2: main comparison ("paper" plan: workload profiles for the normal scenario only;
% fault scenarios on the diurnal workload -- sized for an 8 GB laptop)
for cl = climates, for wl = workloads, for sc = ["normal" "chiller" "pump"], for sd = seeds, for md = ["fixed" "empc" "haempc"]
    if plan == "paper" && sc ~= "normal" && wl ~= "diurnal", continue; end
    rows(end+1, :) = add("E1E2", cl, wl, sc, sd, md, 1.0); %#ok<AGROW>
end, end, end, end, end
% E3: ablations (fault scenarios, diurnal workload, both climates)
for cl = climates, for sc = ["chiller" "pump"], for sd = seeds, for md = ["ha_noHI" "ha_noRUL" "ha_noPrecool"]
    rows(end+1, :) = add("E3", cl, "diurnal", sc, sd, md, 1.0); %#ok<AGROW>
end, end, end, end
% E4: RUL estimation error (pessimistic 0.5x ... optimistic 2x), Pune, diurnal
rs_list = [0.5 0.75 1.25 1.5 2.0];
if plan == "paper", rs_list = [0.5 1.5 2.0 3.0]; end
if plan == "smoke", rs_list = 2.0; end
for sc = ["chiller" "pump"], for sd = seeds, for rs = rs_list
    rows(end+1, :) = add("E4", "pune", "diurnal", sc, sd, "haempc", rs); %#ok<AGROW>
end, end, end
S = finish(rows);
end
function S = finish(rows)
S = cell2table(rows, 'VariableNames', {'experiment','climate','workload','scenario','seed','mode','rul_scale'});
S.experiment = string(S.experiment); S.climate = string(S.climate); S.workload = string(S.workload);
S.scenario = string(S.scenario); S.mode = string(S.mode);
S.start_day = 15 + 36*(S.seed - 1);
S.key = S.climate + "|" + S.workload + "|" + S.scenario + "|" + string(S.seed) + "|" + S.mode + "|" + string(S.rul_scale);
[~, iu] = unique(S.key, 'stable'); S = S(iu, :);
end
