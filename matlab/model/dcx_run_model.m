function [L, out] = dcx_run_model(P, FT, T, opts)
%DCX_RUN_MODEL Simulate DCX_Facility.slx for T seconds and return the same
%   log struct as dcx_sim_matlab (for cross-verification and experiments).
%   Simulink sample at time t corresponds to plant step k = t + 1.
arguments
    P struct
    FT (32,9) double = zeros(32,9)
    T (1,1) double = 3600
    opts.Model (1,1) string = "DCX_Facility"
    opts.SP struct = struct()
    opts.Bridge (1,1) double = 0
end
mdl = char(opts.Model);
load_system(mdl);
assignin('base', 'P', P);
dcx_model_data(P);
in = Simulink.SimulationInput(mdl);
in = in.setVariable('P', P).setVariable('FT', FT).setVariable('BRIDGE', opts.Bridge);
if ~isempty(fieldnames(opts.SP)), in = in.setVariable('SP', opts.SP); end
[Y0, X0] = dcx_bootstrap(P);
in = in.setVariable('X0', X0).setVariable('Y0', Y0);
n = size(P.ou_noise,1);
in = in.setVariable('dcx_ou', [(0:n-1)'*P.dt, P.ou_noise]);
in = in.setModelParameter('StopTime', num2str(T - 1));
out = sim(in);
g = @(bus, f) sig(out.logsout.get(bus).Values.(f));
L.t   = out.logsout.get('E').Values.P_it.Time + 1;
L.it  = g('E','P_it');  L.fac = g('E','P_fac'); L.pue = g('E','pue'); L.cool = g('E','P_cool');
L.max_in = g('A','max_in'); L.Tha = g('A','Tha'); L.Tca = g('A','Tca'); L.Tin = g('A','Tin');
L.fan = g('A','fan'); L.valve = g('A','valve');
L.Tchws = g('C','Tchws'); L.Tchwr = g('C','Tchwr'); L.Qhx = g('C','Qhx'); L.Qch = g('C','Qc'); L.cop = g('C','cop');
L.Tctl = g('C','Tctl');
L.q = g('H','q'); L.H = g('H','H'); L.pump_kw = g('H','P'); L.vib_p = g('H','vib');
L.meas = sig(out.logsout.get('meas').Values); L.truth = sig(out.logsout.get('truth').Values); L.st = sig(out.logsout.get('st').Values);
L.soc = g('E','soc'); L.E_fac = g('E','E_fac'); L.CO2 = g('E','CO2'); L.bus = g('O','bus');
end

function d = sig(ts)
d = ts.Data;
if ndims(d) == 3, d = permute(d, [3 2 1]); d = reshape(d, size(d,1), []); end   % 1xKxN -> NxK
if size(d,1) ~= numel(ts.Time), d = d.'; end
end
