function FT = dcx_fault_table(varargin)
%DCX_FAULT_TABLE Build the fixed-size (32x9) fault table used by DCX_Facility.
%   FT = dcx_fault_table()                         % healthy
%   FT = dcx_fault_table('pump_bearing','P-01', 'Severity',0.9,'Ramp',1200, ...)
%   FT = dcx_fault_table(FT, kind, asset, ...)     % append to an existing table
%   Name-value: Severity (1), T0 (0), Onset (0), Ramp (0), Duration (-1 = permanent),
%   P1 (0), P2 (0).  Asset ids follow the registry ('P-01','CRAH-02','CH-01',
%   'CT-01','BAT-A','UPS-B','R-06','DCX','HX-01','TX-01').
KINDS = {'pump_bearing','pump_cavitation','pump_efficiency','pump_trip','fan_imbalance', ...
    'fan_bearing','crah_trip','crah_filter_blockage','hx_fouling','chiller_degradation', ...
    'chiller_trip','tower_degradation','battery_degradation','battery_overheat','sensor_drift', ...
    'sensor_fail','utility_failure','ups_battery_mode','it_load_increase','rack_overheat','workload_placement'};
if nargin >= 1 && isnumeric(varargin{1})
    FT = varargin{1}; varargin(1) = [];
else
    FT = zeros(32,9);
end
if isempty(varargin), return; end
kind = varargin{1}; asset = varargin{2};
p = inputParser;
addParameter(p,'Severity',1); addParameter(p,'T0',0); addParameter(p,'Onset',0);
addParameter(p,'Ramp',0); addParameter(p,'Duration',-1); addParameter(p,'P1',0); addParameter(p,'P2',0);
parse(p, varargin{3:end}); o = p.Results;
k = find(strcmp(KINDS, kind), 1);
if isempty(k), error('dcx:fault','unknown fault kind %s', kind); end
row = find(FT(:,1) == 0, 1);
if isempty(row), error('dcx:fault','fault table full (32 rows)'); end
FT(row,:) = [k dcx_asset_index(asset) o.Severity o.T0 o.Onset o.Ramp o.Duration o.P1 o.P2];
end

function i = dcx_asset_index(id)
if any(strcmp(id, {'DCX','HX-01','TX-01'})), i = 0; return; end
if strcmp(id,'UPS-A') || strcmp(id,'BAT-A'), i = 1; return; end
if strcmp(id,'UPS-B') || strcmp(id,'BAT-B'), i = 2; return; end
tok = regexp(id, '(\d+)$', 'tokens', 'once');
if isempty(tok), error('dcx:fault','cannot index asset %s', id); end
i = str2double(tok{1});
end
