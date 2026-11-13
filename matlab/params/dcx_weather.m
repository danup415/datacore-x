function W = dcx_weather(site, opts)
%DCX_WEATHER Download an hourly weather year for a site and save
%   params/weather_<site>.mat (dry bulb, RH, wet bulb by Stull 2011).
%   Source: Open-Meteo historical archive (ERA5-based reanalysis).
%   W = dcx_weather("frankfurt")   W = dcx_weather("pune")
arguments
    site (1,1) string
    opts.Year (1,1) double = 2025
end
sites = struct('pune', [18.52 73.86 0.727], 'frankfurt', [50.11 8.68 0.363]);
% third column: grid emission factor kg CO2/kWh used for that site (see params/README_sources.md)
if ~isfield(sites, site), error('dcx:site', 'unknown site %s', site); end
ll = sites.(site);
url = sprintf(['https://archive-api.open-meteo.com/v1/archive?latitude=%.2f&longitude=%.2f' ...
    '&start_date=%d-01-01&end_date=%d-12-31&hourly=temperature_2m,relative_humidity_2m&timezone=auto'], ...
    ll(1), ll(2), opts.Year, opts.Year);
J = webread(url, weboptions('Timeout', 60));
T = fillmissing(J.hourly.temperature_2m(:), 'linear'); RH = fillmissing(J.hourly.relative_humidity_2m(:), 'linear');
Tw = T.*atan(0.151977*sqrt(RH + 8.313659)) + atan(T + RH) - atan(RH - 1.676331) ...
     + 0.00391838*RH.^1.5.*atan(0.023101*RH) - 4.686035;
n = min(8760, numel(T));
W = struct('site', char(site), 'lat', ll(1), 'lon', ll(2), 'year', opts.Year, 'db', T(1:n)', 'wb', Tw(1:n)', 'rh', RH(1:n)', ...
    'grid_ef_kg_per_kwh', ll(3), 'source', sprintf('Open-Meteo historical archive (ERA5-based), %s %d, hourly; wet bulb Stull (2011)', site, opts.Year), ...
    'stats', struct('db_mean', mean(T), 'db_max', max(T), 'wb_mean', mean(Tw), 'wb_max', max(Tw), 'wb_p996', prctile(Tw, 99.6), ...
                    'hours_wb_below_12', sum(Tw < 12)));
save(fullfile(fileparts(mfilename('fullpath')), sprintf('weather_%s.mat', site)), 'W');
fprintf('%s %d: db mean %.1f max %.1f C; wb mean %.1f max %.1f C; %d h with wb < 12 C\n', site, opts.Year, ...
    W.stats.db_mean, W.stats.db_max, W.stats.wb_mean, W.stats.wb_max, W.stats.hours_wb_below_12);
end
