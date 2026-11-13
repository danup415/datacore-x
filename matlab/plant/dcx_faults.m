function F = dcx_faults(t, FT)
%DCX_FAULTS Fault-injection severities at time t (code-generation compatible).
%   FT is a fixed-size 32x9 table, one row per fault:
%   [kind asset severity t0 onset ramp duration p1 p2]   (duration<0 = permanent)
%   Kind codes (see dcx_fault_table): 1 pump_bearing 2 pump_cavitation
%   3 pump_efficiency(p1=drop) 4 pump_trip 5 fan_imbalance 6 fan_bearing
%   7 crah_trip 8 crah_filter_blockage 9 hx_fouling 10 chiller_degradation
%   11 chiller_trip 12 tower_degradation 13 battery_degradation
%   14 battery_overheat 15 sensor_drift(p1=bias K) 16 sensor_fail
%   17 utility_failure 18 ups_battery_mode(asset 0=both) 19 it_load_increase
%   20 rack_overheat(p1=extra kW) 21 workload_placement(p1=strategy 1..3)
F = struct('pump_brg',zeros(1,3),'pump_cav',zeros(1,3),'pump_effdrop',zeros(1,3),'pump_trip',zeros(1,3), ...
    'fan_imb',zeros(1,4),'fan_brg',zeros(1,4),'crah_trip',zeros(1,4),'crah_block',zeros(1,4), ...
    'hx_foul',0,'ch_deg',zeros(1,2),'ch_trip',zeros(1,2),'tower_deg',zeros(1,2), ...
    'bat_deg',zeros(1,2),'bat_ovh',zeros(1,2),'drift',zeros(1,8),'sfail',zeros(1,8), ...
    'utility',0,'ups_batt',zeros(1,2),'it_inc',0,'rack_ovh',zeros(1,8),'rack_extra',zeros(1,8), ...
    'placement',0);
for r = 1:size(FT,1)
    k = FT(r,1);
    if k <= 0, continue; end
    a = max(1, FT(r,2));
    tt = t - FT(r,4) - FT(r,5);
    s = 0;
    if tt >= 0 && (FT(r,7) < 0 || tt <= FT(r,7))
        if FT(r,6) <= 0, s = FT(r,3); else, s = FT(r,3)*min(1, tt/FT(r,6)); end
    end
    if s <= 0, continue; end
    switch k
        case 1,  F.pump_brg(a)  = max(F.pump_brg(a), s);
        case 2,  F.pump_cav(a)  = max(F.pump_cav(a), s);
        case 3,  F.pump_effdrop(a) = max(F.pump_effdrop(a), s*FT(r,8));
        case 4,  F.pump_trip(a) = 1;
        case 5,  F.fan_imb(a)   = max(F.fan_imb(a), s);
        case 6,  F.fan_brg(a)   = max(F.fan_brg(a), s);
        case 7,  F.crah_trip(a) = 1;
        case 8,  F.crah_block(a)= max(F.crah_block(a), s);
        case 9,  F.hx_foul      = max(F.hx_foul, s);
        case 10, F.ch_deg(a)    = max(F.ch_deg(a), s);
        case 11, F.ch_trip(a)   = 1;
        case 12, F.tower_deg(a) = max(F.tower_deg(a), s);
        case 13, F.bat_deg(a)   = max(F.bat_deg(a), s);
        case 14, F.bat_ovh(a)   = max(F.bat_ovh(a), s);
        case 15, F.drift(a)     = F.drift(a) + s*FT(r,8);
        case 16, F.sfail(a)     = 1;
        case 17, F.utility      = 1;
        case 18
            if FT(r,2) == 0, F.ups_batt(:) = 1; else, F.ups_batt(a) = 1; end
        case 19, F.it_inc       = max(F.it_inc, s);
        case 20
            F.rack_ovh(a) = max(F.rack_ovh(a), s);
            F.rack_extra(a) = max(F.rack_extra(a), s*FT(r,8));
        case 21, F.placement    = FT(r,8);
    end
end
end
