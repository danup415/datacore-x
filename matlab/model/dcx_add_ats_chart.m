function blk = dcx_add_ats_chart(sys, name, pos)
%DCX_ADD_ATS_CHART Add the Stateflow chart that sequences the standby
%   generator and the automatic transfer switch (item 2).
%   Parallel (AND) states, executed Generator first, then ATS:
%     Generator : STOPPED -> STARTING -> RUNNING -> COOLDOWN -> STOPPED
%     ATS       : UTIL -> DEAD -> WAIT -> GEN -> RETRANSFER -> UTIL
%   Input  grid_ok (1 = utility healthy)
%   Output bus (0 dead, 1 utility, 2 generator), gen_state (0..3)
%   Timers are tick counts at Ts = 1 s and reproduce dcx_plc step-for-step:
%     generator RUNNING gen_start_s after loss, ATS closes to GEN ats_s
%     after the generator is RUNNING, retransfer retransfer_s after the
%     utility returns, generator stops cooldown_s after retransfer.
%   Constants are chart parameters ats_gen_start_s, ats_ats_s,
%   ats_retransfer_s, ats_cooldown_s (base workspace, set by dcx_model_data).
blk = [sys '/' name];
add_block('sflib/Chart', blk, 'Position', pos);
c = find(sfroot, '-isa', 'Stateflow.Chart', 'Path', blk);
c.ActionLanguage = 'MATLAB';
c.ChartUpdate = 'DISCRETE'; c.SampleTime = '1';
c.Decomposition = 'PARALLEL_AND';
% ---- data
d = Stateflow.Data(c); d.Name = 'grid_ok'; d.Scope = 'Input'; d.DataType = 'double';
d = Stateflow.Data(c); d.Name = 'bus'; d.Scope = 'Output'; d.DataType = 'double'; d.Props.InitialValue = '1';
d = Stateflow.Data(c); d.Name = 'gen_state'; d.Scope = 'Output'; d.DataType = 'double'; d.Props.InitialValue = '0';
d = Stateflow.Data(c); d.Name = 'rt'; d.Scope = 'Local'; d.DataType = 'double'; d.Props.InitialValue = '0';
for p = {'ats_gen_start_s','ats_ats_s','ats_retransfer_s','ats_cooldown_s'}
    d = Stateflow.Data(c); d.Name = p{1}; d.Scope = 'Parameter'; d.DataType = 'double';
end
% ---- Generator
G = Stateflow.State(c); G.Name = 'Generator'; G.Position = [20 20 760 290];
G.Decomposition = 'EXCLUSIVE_OR'; G.ExecutionOrder = 1;
gs = st(G, 'STOPPED',  'entry: gen_state = 0;', [60 80 150 60]);
gS = st(G, 'STARTING', 'entry: gen_state = 1;', [320 80 150 60]);
gR = st(G, 'RUNNING',  'entry: gen_state = 2;', [580 80 150 60]);
gC = st(G, 'COOLDOWN', 'entry: gen_state = 3;', [320 220 150 60]);
dflt(G, gs, [135 55]);
tr(G, gs, gS, '[grid_ok == 0]', 1, 2.5, 9.5, [265 88]);
tr(G, gS, gs, '[grid_ok ~= 0]', 1, 8.5, 3.5, [265 132]);
tr(G, gS, gR, '[after(ats_gen_start_s - 1, tick)]', 2, 3, 9, [525 100]);
tr(G, gR, gC, '[grid_ok ~= 0 && in(ATS.RETRANSFER) && rt + 1 >= ats_retransfer_s]', 1, 6, 3, [640 250]);
tr(G, gC, gS, '[grid_ok == 0]', 1, 12, 6, [395 180]);
tr(G, gC, gs, '[after(ats_cooldown_s - 1, tick)]', 2, 9, 6, [135 250]);
% ---- ATS
A = Stateflow.State(c); A.Name = 'ATS'; A.Position = [20 330 760 320];
A.Decomposition = 'EXCLUSIVE_OR'; A.ExecutionOrder = 2;
aU = st(A, 'UTIL', 'entry: bus = 1;', [60 420 150 60]);
aD = st(A, 'DEAD', 'entry: bus = 0;', [320 420 150 60]);
aW = st(A, 'WAIT', 'entry: bus = 0;', [580 420 150 60]);
aG = st(A, 'GEN',  'entry: bus = 2;', [580 560 150 60]);
aR = st(A, 'RETRANSFER', sprintf('entry: bus = 2; rt = 1;\nduring: rt = rt + 1;'), [320 560 170 70]);
dflt(A, aU, [135 395]);
tr(A, aU, aD, '[grid_ok == 0]', 1, 2.5, 9.5, [265 428]);
tr(A, aD, aU, '[grid_ok ~= 0]', 1, 8.5, 3.5, [265 472]);
tr(A, aD, aW, '[in(Generator.RUNNING)]', 2, 3, 9, [525 450]);
tr(A, aW, aU, '[grid_ok ~= 0]', 1, 12, 12, [395 375]);
tr(A, aW, aG, '[after(ats_ats_s - 1, tick)]', 2, 6, 12, [655 520]);
tr(A, aG, aR, '[grid_ok ~= 0]', 1, 8.5, 2.5, [535 572]);
tr(A, aR, aG, '[grid_ok == 0]', 1, 3.5, 9.5, [535 618]);
tr(A, aR, aU, '[rt + 1 >= ats_retransfer_s]', 2, 9, 6, [135 595]);
end

function s = st(parent, name, body, pos)
s = Stateflow.State(parent); s.LabelString = sprintf('%s\n%s', name, body); s.Position = pos;
end
function dflt(parent, dst, xy)
t = Stateflow.Transition(parent); t.Destination = dst; t.DestinationOClock = 0;
t.SourceEndpoint = xy; t.MidPoint = xy + [0 10];
end
function tr(parent, a, b, label, order, so, do, mid)
t = Stateflow.Transition(parent); t.Source = a; t.Destination = b; t.LabelString = label;
t.ExecutionOrder = order;
t.SourceOClock = so; t.DestinationOClock = do;
t.MidPoint = mid;
t.LabelPosition = [mid(1) - 60, mid(2) - 14, 120, 14];
end
