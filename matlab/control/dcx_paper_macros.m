function dcx_paper_macros(opts)
%DCX_PAPER_MACROS Write paper/macros_results.tex and paper/tables/*.tex from
%   the study statistics (dcx_study_stats) and credibility results
%   (dcx_credibility), and copy the figures into paper/figures. Every number
%   quoted in the manuscript comes from here; missing values print [TBD].
arguments
    opts.Plan (1,1) string = "full"
    opts.Paper (1,1) string = ""
end
here = fileparts(mfilename('fullpath')); root = fileparts(here);
paper = opts.Paper; if paper == "", paper = fullfile(fileparts(root), 'paper'); end
if ~isfolder(fullfile(paper, 'tables')), mkdir(fullfile(paper, 'tables')); end
if ~isfolder(fullfile(paper, 'figures')), mkdir(fullfile(paper, 'figures')); end
M = containers.Map();
st = fullfile(here, 'results', 'study', sprintf('stats_%s.mat', opts.Plan));
if isfile(st)
    S = load(st); S = S.S;
    M('nRuns') = sprintf('%d', S.wall.runs); M('cpuHours') = sprintf('%.0f', S.wall.total_h);
    % ---- E1
    for cl = ["pune" "frankfurt" "all"]
        tag = capital(cl);
        for cmp = ["haempc - fixed" "haempc - empc" "empc - fixed"]
            ct = replace(replace(cmp, "haempc", "Ha"), "empc", "Empc"); ct = replace(replace(ct, " - ", ""), "fixed", "Fixed");
            for met = ["cooling_kwh" "energy_kwh" "pue"]
                mt = containers.Map({'cooling_kwh','energy_kwh','pue'}, {'Cool','Fac','Pue'}); mt = mt(char(met));
                x = S.E1diff(S.E1diff.climate == cl & S.E1diff.comparison == cmp & S.E1diff.metric == met, :);
                if isempty(x), continue; end
                k = "Eone" + mt + "Rel" + ct + tag;
                M(char(k)) = sprintf('%.1f', x.rel_pct); M(char(k + "Lo")) = sprintf('%.1f', x.rel_lo); M(char(k + "Hi")) = sprintf('%.1f', x.rel_hi);
                M(char("Eone" + mt + "P" + ct + tag)) = pfmt(x.p_wilcoxon);
            end
        end
        for md = ["fixed" "empc" "haempc"]
            x = S.E1(S.E1.climate == cl & S.E1.workload == "all" & S.E1.mode == md, :);
            if isempty(x), continue; end
            mtag = containers.Map({'fixed','empc','haempc'}, {'Fixed','Empc','Ha'}); mtag = mtag(char(md));
            M(char("EonePue" + mtag + tag)) = sprintf('%.3f', x.pue);
            M(char("EoneTtwentyEight" + mtag + tag)) = sprintf('%.1f', x.t_above_28_s/60);
        end
    end
    % ---- E2 (pooled over scenarios and climates)
    for md = ["fixed" "empc" "haempc"]
        x = S.E2(S.E2.mode == md, :);
        mtag = containers.Map({'fixed','empc','haempc'}, {'Fixed','Empc','Ha'}); mtag = mtag(char(md));
        M(char("EtwoTrips" + mtag)) = sprintf('%d/%d', sum(x.n_trip), sum(x.n));
        xp = x(x.scenario == "pump", :);
        M(char("EtwoRisk" + mtag)) = sprintf('%.1f', sum(xp.risk_min.*xp.n)/sum(xp.n));
    end
    x = S.E2diff(S.E2diff.scenario == "all" & S.E2diff.comparison == "haempc - empc" & S.E2diff.metric == "energy_kwh", :);
    if ~isempty(x)
        M('EtwoEnergyRelHaEmpc') = sprintf('%.1f', x.rel_pct); M('EtwoEnergyRelHaEmpcLo') = sprintf('%.1f', x.rel_lo);
        M('EtwoEnergyRelHaEmpcHi') = sprintf('%.1f', x.rel_hi);
    end
    % ---- E3 summary sentence
    a = S.E3(S.E3.scenario == "all", :); s = "";
    names = containers.Map({'haempc','ha_noHI','ha_noRUL','ha_noPrecool','empc'}, {'the full controller','removing the HI','removing RUL','removing pre-cooling','health-blind EMPC'});
    parts = strings(0);
    for i = 1:height(a)
        parts(end+1) = sprintf('%s: %d/%d unplanned trips, %.1f\\,min zone-C/D exposure, peak inlet %.2f\\,\\textdegree C', ...
            names(char(a.variant(i))), a.n_trip(i), a.n(i), a.risk_min(i), a.peak_c(i)); %#ok<AGROW>
    end
    if ~isempty(parts), s = "Across both fault scenarios and climates: " + strjoin(parts, "; ") + "."; end
    M('EthreeSummary') = char(s);
    % ---- E4 summary
    b = S.E4; parts = strings(0);
    for sc = ["chiller" "pump"]
        y = b(b.scenario == sc, :);
        parts(end+1) = sprintf('%s fault: trip rate %s at RUL errors of %s\\,\\%%', sc, ...
            strjoin(compose('%.2f', y.trip_rate), '/'), strjoin(compose('%+.0f', y.rul_error_pct), '/')); %#ok<AGROW>
    end
    M('EfourSummary') = char("\Cref{tab:E4} and \cref{fig:E34} (right) report the effect of RUL error. " + strjoin(parts, "; ") + ".");
    % ---- E6
    e = S.E6(S.E6.mode ~= "fixed", :);
    M('EsixMeanMs') = sprintf('%.0f', sum(e.mean_ms.*e.solves)/sum(e.solves)); M('EsixMaxMs') = sprintf('%.0f', max(e.max_ms));
    % ---- copy tables / figures
    tdir = fullfile(here, 'results', 'study', 'tables'); fdir = fullfile(here, 'results', 'study', 'figures');
    for t = ["tab_E1" "tab_E2" "tab_E3" "tab_E4" "tab_E6"], copyfile(fullfile(tdir, t + ".tex"), fullfile(paper, 'tables')); end
    for f = ["fig_E1_cooling_savings" "fig_E3E4_risk"], copyfile(fullfile(fdir, f + ".pdf"), fullfile(paper, 'figures')); end
end
% ---- E5 (cluster-bootstrap CIs from dcx_e5_ci)
ef = fullfile(root, 'pdm', 'models', 'dcx_e5_ci.mat');
if isfile(ef)
    E = load(ef); E = E.E; G = E.diag;
    tg = containers.Map({'pump','crah','plant'}, {'Pump','Crah','Plant'});
    for d = ["pump" "crah" "plant"]
        b = G(G.domain == d & G.features == "sensor+physics", :); a = G(G.domain == d & G.features == "sensor-only", :);
        M(char("Efive" + tg(char(d)))) = sprintf('%.3f', b.macroF1);
        M(char("Efive" + tg(char(d)) + "Lo")) = sprintf('%.3f', b.ci_lo); M(char("Efive" + tg(char(d)) + "Hi")) = sprintf('%.3f', b.ci_hi);
        M(char("Efive" + tg(char(d)) + "Sensor")) = sprintf('%.3f', a.macroF1);
    end
    x = E.rul(E.rul.model == "exponential", :);
    M('EfiveRulRmse') = sprintf('%.1f', x.RMSE_min); M('EfiveRulRmseLo') = sprintf('%.1f', x.ci_lo); M('EfiveRulRmseHi') = sprintf('%.1f', x.ci_hi);
    M('EfiveRulLate') = sprintf('%.1f', x.RMSE_late_min); M('EfiveRulCover') = sprintf('%.2f', x.CI90_coverage);
    M('EfiveRulRuns') = sprintf('%d', x.test_runs);
    copyfile(fullfile(here, 'results', 'study', 'tables', 'tab_E5.tex'), fullfile(paper, 'tables'));
end
% ---- credibility
cr = fullfile(here, 'results', 'credibility');
if isfile(fullfile(cr, 'energy_balance.csv'))
    B = readtable(fullfile(cr, 'energy_balance.csv'), 'TextType', 'string');
    fid = fopen(fullfile(paper, 'tables', 'tab_balance.tex'), 'w');
    fprintf(fid, '\\begin{tabular}{lrrrrrr}\n\\toprule\nClimate & Room air, raw (\\%%) & Recirculation term (\\%% of coil) & Room air, closed (\\%%) & CHW loop (\\%%) & Condenser (\\%%) & Energy meter (\\%%)\\\\\n\\midrule\n');
    for i = 1:height(B)
        fprintf(fid, '%s & %.2f & %.2f & %.2f & %.3f & %.3f & %.4f\\\\\n', capital(B.climate(i)), B.room_residual_raw_pct(i), B.recirc_term_pct_of_coil(i), ...
            B.room_residual_pct(i), B.chw_residual_pct(i), B.condenser_residual_pct(i), B.energy_meter_vs_integral_pct(i));
    end
    M('CredRecircPct') = sprintf('%.1f', mean(B.recirc_term_pct_of_coil)); M('CredRoomRaw') = sprintf('%.1f', mean(B.room_residual_raw_pct));
    M('CredRoomClosed') = sprintf('%.2f', max(abs(B.room_residual_pct)));
    fprintf(fid, '\\bottomrule\n\\end{tabular}\n'); fclose(fid);
    Sx = readtable(fullfile(cr, 'step_responses.csv'), 'TextType', 'string');
    g = @(st, sg) Sx.settling_min(contains(Sx.step, st) & Sx.signal == sg);
    try
        M('CredSettleChws') = sprintf('%.0f', g("CHW", "Tchws")); M('CredSettleSat') = sprintf('%.1f', g("Supply-air", "Tsup (mean)"));
        x = Sx(contains(Sx.step, "IT") & Sx.signal == "max inlet", :);
        M('CredItPeakInlet') = sprintf('%.2f', x.peak_deviation); M('CredItRecover') = sprintf('%.0f', x.settling_min);
    catch
    end
    for f = ["fig_step_responses" "fig_calibration"], copyfile(fullfile(cr, f + ".pdf"), fullfile(paper, 'figures')); end
end
% ---- write macros (all names used in main.tex; missing -> [TBD])
need = ["nRuns" "cpuHours" "EoneCoolRelHaFixedPune" "EoneCoolRelHaFixedPuneLo" "EoneCoolRelHaFixedPuneHi" ...
    "EoneCoolRelHaFixedFrankfurt" "EoneCoolRelHaFixedFrankfurtLo" "EoneCoolRelHaFixedFrankfurtHi" ...
    "EoneFacRelHaFixedPune" "EoneFacRelHaFixedFrankfurt" "EoneCoolRelHaEmpcAll" "EoneCoolRelHaEmpcAllLo" "EoneCoolRelHaEmpcAllHi" ...
    "EoneCoolPHaEmpcAll" "EtwoTripsFixed" "EtwoTripsEmpc" "EtwoTripsHa" "EtwoRiskEmpc" "EtwoRiskHa" ...
    "EtwoEnergyRelHaEmpc" "EtwoEnergyRelHaEmpcLo" "EtwoEnergyRelHaEmpcHi" "EthreeSummary" "EfourSummary" ...
    "EfivePump" "EfiveCrah" "EfivePlant" "EsixMeanMs" "EsixMaxMs" "CredSettleChws" "CredSettleSat" ...
    "CredRecircPct" "CredRoomRaw" "CredRoomClosed" "CredItPeakInlet" "CredItRecover" ...
    "EfivePumpLo" "EfivePumpHi" "EfiveCrahLo" "EfiveCrahHi" "EfivePlantLo" "EfivePlantHi" "EfivePumpSensor" "EfiveCrahSensor" "EfivePlantSensor" ...
    "EfiveRulRmse" "EfiveRulRmseLo" "EfiveRulRmseHi" "EfiveRulLate" "EfiveRulCover" "EfiveRulRuns"];
fid = fopen(fullfile(paper, 'macros_results.tex'), 'w');
fprintf(fid, '%% generated by dcx_paper_macros.m on %s -- do not edit\n', string(datetime('now')));
ks = unique([need, string(M.keys)]);
for k = ks
    if isKey(M, char(k)), v = M(char(k)); else, v = '\textbf{[TBD]}'; end
    fprintf(fid, '\\newcommand{\\%s}{%s}\n', k, v);
end
fclose(fid);
fprintf('[paper] wrote %d macros (%d missing) to %s\n', numel(ks), sum(~isKey(M, cellstr(ks))), paper);
end

function s = capital(x), x = string(x); s = upper(extractBefore(x, 2)) + extractAfter(x, 1); end
function s = pfmt(p)
if p < 0.001, s = '<0.001'; else, s = sprintf('%.3f', p); end
end
