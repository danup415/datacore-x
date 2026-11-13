function T = ims_extract(root, out, which)
%IMS_EXTRACT Condition indicators for every snapshot of the NASA IMS bearing run-to-failure tests.
%   T = ims_extract('C:\...\data\raw\ims', 'C:\...\data\ims_features.csv')
%   Expects the three test folders (any nesting): 1st_test, 2nd_test, and the third test
%   (shipped as 3rd_test\4th_test\txt). One row per snapshot and bearing.
%
%   Rig (IMS readme): four Rexnord ZA-2115 double-row bearings on one shaft, 2000 rpm, 6000 lb radial
%   load, 20 kHz, 20480-point snapshots (about 1 s), every 10 min (test 1: partly every 5 min).
%   Test 1 has two accelerometers per bearing (x, y); tests 2 and 3 have one.
%   Geometry for defect frequencies (Qiu, Lee, Lin, J. Sound Vib. 289 (2006), the readme's reference
%   paper): 16 rollers per row, roller 0.331 in, pitch diameter 2.815 in, contact angle 15.17 deg.
%   which: tests to process, default [2 1 3] (test 3 has the most files).
if nargin < 2 || isempty(out), out = fullfile(fileparts(root), 'ims_features.csv'); end
if nargin < 3, which = [2 1 3]; end
g = struct('n', 16, 'd', 0.331, 'D', 2.815, 'theta', 15.17);
fr = vib_bearing_freqs(g, 2000);
fs = 20480;
tests = {'1st_test', 8; '2nd_test', 4; '4th_test', 4};
rows = {};
for k = which
    d = find_dir(root, tests{k, 1});
    if strcmp(tests{k, 1}, '4th_test') && isfolder(fullfile(d, 'txt')), d = fullfile(d, 'txt'); end
    f = dir(fullfile(d, '20*'));
    f = f(~[f.isdir]);
    [~, ix] = sort({f.name}); f = f(ix);
    fprintf('[ims] test %d: %d files in %s\n', k, numel(f), d);
    for i = 1:numel(f)
        try
            fid = fopen(fullfile(d, f(i).name)); x = fscanf(fid, '%f'); fclose(fid);
            x = reshape(x, tests{k, 2}, []).';
        catch err
            fprintf('[ims]   skipped %s: %s\n', f(i).name, err.message);
            continue
        end
        ts = datetime(f(i).name, 'InputFormat', 'yyyy.MM.dd.HH.mm.ss');
        for b = 1:4
            ch = b; if tests{k, 2} == 8, ch = 2*b - 1; end      % test 1: x-channel of each bearing
            F = vib_features(x(:, ch), fs, fr);
            rows(end+1, :) = {k, b, i, char(ts, 'yyyy-MM-dd HH:mm:ss'), F.rms_g, F.peak_g, F.crest, F.kurtosis, ...
                F.vrms_mms, F.e_lo, F.e_mid, F.e_hi, F.band_lo, F.band_hi, F.BPFO_snr, F.BPFI_snr, F.BSF_snr, F.FTF_snr, ...
                F.env_BPFO, F.env_BPFI, F.env_BSF}; %#ok<AGROW>
        end
        if mod(i, 500) == 0          % checkpoint, so an interrupted run keeps its work
            writetable(cell2table(rows), [out '.partial.csv']);
        end
        if mod(i, 100) == 0
            fprintf('[ims]   test %d: %d/%d\n', k, i, numel(f));
            pf = fopen([out '.progress.txt'], 'w'); fprintf(pf, 'test %d: %d/%d\n', k, i, numel(f)); fclose(pf);
        end
    end
end
T = cell2table(rows, 'VariableNames', {'test', 'bearing', 'idx', 'time', 'rms_g', 'peak_g', 'crest', 'kurtosis', ...
    'vrms_mms', 'e_lo', 'e_mid', 'e_hi', 'band_lo', 'band_hi', 'BPFO_snr', 'BPFI_snr', 'BSF_snr', 'FTF_snr', ...
    'env_BPFO', 'env_BPFI', 'env_BSF'});
writetable(T, out);
fprintf('[ims] wrote %s (%d rows); BPFO %.1f BPFI %.1f 2xBSF %.1f FTF %.1f Hz\n', out, height(T), fr.BPFO, fr.BPFI, 2*fr.BSF, fr.FTF);
end

function d = find_dir(root, name)
L = dir(fullfile(root, '**', name));
L = L([L.isdir] & ~ismember({L.name}, {'.', '..'}));
if isempty(L)
    L = dir(fullfile(root, '**'));
    L = L([L.isdir] & strcmp({L.name}, name));
end
if isempty(L), error('ims_extract:missing', 'folder %s not found under %s', name, root); end
% the deepest match holds the files (archives sometimes nest a folder of the same name)
[~, j] = max(cellfun(@numel, {L.folder}));
d = fullfile(L(j).folder, L(j).name);
end
