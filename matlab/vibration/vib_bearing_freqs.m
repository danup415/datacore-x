function f = vib_bearing_freqs(g, rpm)
%VIB_BEARING_FREQS Bearing defect frequencies (Hz) from geometry and shaft speed.
%   g: struct with fields
%       n      number of rolling elements (per row)
%       d      rolling-element diameter
%       D      pitch diameter (same unit as d)
%       theta  contact angle in degrees
%   rpm: shaft speed (rev/min)
%   f: struct with fr, BPFO, BPFI, BSF, FTF (Hz) and the multipliers of shaft speed (x*).
%
%   BPFO = n/2 fr (1 - d/D cos th)      outer-race defect
%   BPFI = n/2 fr (1 + d/D cos th)      inner-race defect
%   BSF  = D/(2d) fr (1 - (d/D cos th)^2)   rolling element (2xBSF often dominant)
%   FTF  = fr/2 (1 - d/D cos th)        cage
fr = rpm/60;
r = g.d/g.D*cosd(g.theta);
f = struct('fr', fr, ...
    'BPFO', g.n/2*fr*(1 - r), 'BPFI', g.n/2*fr*(1 + r), ...
    'BSF', g.D/(2*g.d)*fr*(1 - r^2), 'FTF', fr/2*(1 - r));
f.xBPFO = f.BPFO/fr; f.xBPFI = f.BPFI/fr; f.xBSF = f.BSF/fr; f.xFTF = f.FTF/fr;
end
