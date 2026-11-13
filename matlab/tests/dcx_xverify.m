function R = dcx_xverify(simfun)
%DCX_XVERIFY Cross-verify the MATLAB/Simulink plant against the Python
%   surrogate (identical inputs, utilisation noise off, 3600 s, 6 scenarios).
%   simfun: @(P,FT,T) -> log struct (default dcx_sim_matlab; DCX_Facility
%   uses dcx_run_model). Returns a table of errors and pass/fail.
if nargin < 1, simfun = @(P,FT,T) dcx_sim_matlab(P,FT,T); end
here = fileparts(mfilename('fullpath')); d = fullfile(here, 'xverify');
P = dcx_params('UtilNoise', false);
P.u_base = jsondecode(fileread(fullfile(d,'py_u_base.json')))';
sc = {'baseline', zeros(32,9);
      'utility', dcx_fault_table('utility_failure','TX-01','Onset',900,'Duration',600);
      'pump_bearing', dcx_fault_table('pump_bearing','P-01','Severity',0.9,'Ramp',1200);
      'chiller_deg', dcx_fault_table('chiller_degradation','CH-01','Severity',0.8,'Ramp',900);
      'it_inc', dcx_fault_table('it_load_increase','DCX','Severity',0.4,'Ramp',300);
      'rack_ovh', dcx_fault_table('rack_overheat','R-06','Ramp',120,'P1',6)};
sig = {'it','fac','pue','max_in','Tchws','Tha','cool'};
tol = [0.02 0.03 0.015 0.6 0.4 0.8 0.08];        % relative for powers/PUE, absolute K for temps
isrel = [1 1 0 0 0 0 1];
rows = {};
for s = 1:size(sc,1)
    py = readtable(fullfile(d, ['py_' sc{s,1} '.csv']));
    L = simfun(P, sc{s,2}, 3600);
    for g = 1:numel(sig)
        a = L.(sig{g}); b = py.(sig{g});
        n = min(numel(a), numel(b)); a = a(1:n); b = b(1:n);
        % event-time tolerance: compare against the Python value within +/-2 s
        % (the Python surrogate updates domains sequentially within a step,
        % the Simulink model with a one-step inter-subsystem delay)
        e = inf(n,1);
        for sh = -2:2
            idx = max(1, min(n, (1:n)' + sh));
            e = min(e, abs(a - b(idx)));
        end
        if isrel(g), e = e ./ max(abs(b), 1); end
        e = e(61:end);                                   % skip 60 s start-up
        p999 = prctile(e, 99.9);          % pass criterion; max reported for transparency
        ok = p999 <= tol(g);
        rows(end+1,:) = {sc{s,1}, sig{g}, mean(e), p999, max(e), tol(g), ok}; %#ok<AGROW>
    end
end
R = cell2table(rows, 'VariableNames', {'scenario','signal','mean_err','p999_err','max_err','tolerance','pass'});
fprintf('Cross-verification: %d/%d checks pass\n', sum(R.pass), height(R));
end
