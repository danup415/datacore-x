function D = dcx_disturbance(t, ou, P)
%DCX_DISTURBANCE Boundary conditions: ambient wet/dry bulb (Pune, November —
%   design assumption, replace with a TMY/ISHRAE weather year in item 3),
%   diurnal IT load swing and OU utilisation noise sample `ou` (1x8).
h = mod(P.start_hour + t/3600, 24);
D.hour = h;
if P.use_weather > 0
    hy = (P.start_day - 1)*24 + P.start_hour + t/3600;          % hour of year
    i0 = mod(floor(hy), 8760) + 1; i1 = mod(i0, 8760) + 1; f = hy - floor(hy);
    D.wb = (1 - f)*P.weather_wb(i0) + f*P.weather_wb(i1);
    D.db = (1 - f)*P.weather_db(i0) + f*P.weather_db(i1);
else
    D.wb = 17.0 - 3.0*cos(2*pi*(h - 5)/24);
    D.db = 23.5 - 6.0*cos(2*pi*(h - 5)/24);
end
% IT utilisation profile (P.workload): 1 diurnal swing, 2 flat, 3 bursty batch/AI-training
% blocks (45 min high / 45 min low, zero mean) on top of the per-rack base utilisation
if P.workload == 2
    D.diurnal = 0.0;
elseif P.workload == 3
    D.diurnal = 0.15*double(mod(t, 5400) < 2700) - 0.075;
else
    D.diurnal = 0.10*sin(2*pi*(h - 9)/24);
end
D.ou = reshape(ou(1:8), 1, 8);
end
