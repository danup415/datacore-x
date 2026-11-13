function R = dcx_test_ats_chart(opts)
%DCX_TEST_ATS_CHART Unit test: the Stateflow ATS_Sequence chart must give the
%   same bus / generator-state trace as the dcx_plc MATLAB logic for a set of
%   utility outage patterns (long outage, short outage before the generator is
%   up, return during retransfer wait, re-loss during cooldown).
arguments, opts.Show (1,1) logical = false, end
P = dcx_params();
T = 900; g = ones(T,1);
g(50:399) = 0;            % long outage -> GEN, retransfer, cooldown
g(430:434) = 0;           % re-loss during cooldown, returns before gen is up
g(480:520) = 0;           % outage; utility returns ...
g(540:545) = 0;           % ... and is lost again during the retransfer wait
% ---- MATLAB reference (dcx_plc path, utility fault only)
S = dcx_initial_state(P); S = S.plc;
FT = zeros(32,9); F0 = dcx_faults(0, FT);
cmd = struct('seq',0,'code',0,'asset',0,'value',0);
ref = zeros(T,2);
for k = 1:T
    F = F0; F.utility = double(g(k) == 0);
    [S, O] = dcx_plc(S, F, [1 1], [0.5 0.5], cmd, P);
    ref(k,:) = [O.bus O.gen_state];
end
% ---- Stateflow chart in a harness model
mdl = 'dcx_ats_harness';
if bdIsLoaded(mdl), close_system(mdl, 0); end
new_system(mdl); 
assignin('base', 'ats_gen_start_s', P.gen_start_s); assignin('base', 'ats_ats_s', P.ats_s);
assignin('base', 'ats_retransfer_s', P.retransfer_s); assignin('base', 'ats_cooldown_s', P.cooldown_s);
assignin('base', 'ats_g', [(1:T)' g]);
add_block('simulink/Sources/From Workspace', [mdl '/g'], 'VariableName', 'ats_g', 'SampleTime', '1', ...
    'Interpolate', 'off', 'OutputAfterFinalValue', 'Holding final value', 'Position', [20 40 80 70]);
dcx_add_ats_chart(mdl, 'ATS_Sequence', [140 30 260 110]);
add_block('simulink/Sinks/Out1', [mdl '/bus'], 'Position', [320 40 350 54]);
add_block('simulink/Sinks/Out1', [mdl '/gen'], 'Position', [320 80 350 94]);
add_line(mdl, 'g/1', 'ATS_Sequence/1'); add_line(mdl, 'ATS_Sequence/1', 'bus/1'); add_line(mdl, 'ATS_Sequence/2', 'gen/1');
set_param(mdl, 'Solver', 'FixedStepDiscrete', 'FixedStep', '1', 'StartTime', '1', 'StopTime', num2str(T), ...
    'SaveOutput', 'on', 'SaveFormat', 'Array', 'ReturnWorkspaceOutputs', 'on');
so = sim(mdl);
y = so.yout;
close_system(mdl, 0);
% chart takes its default transitions on the first tick; compare from k = 2
k = 2:T;
mis = find(any(y(k,:) ~= ref(k,:), 2));
R = struct('n', numel(k), 'mismatches', numel(mis), 'pass', isempty(mis), 'ref', ref, 'chart', y);
fprintf('ATS chart vs dcx_plc: %d steps, %d mismatches -> %s\n', numel(k), numel(mis), string(R.pass));
if ~isempty(mis)
    i = k(mis(1)); fprintf('first mismatch at t=%d: ref [%d %d] chart [%d %d]\n', i, ref(i,:), y(i,:));
end
if opts.Show
    figure; stairs([ref y]); legend('bus ref','gen ref','bus chart','gen chart');
end
end
