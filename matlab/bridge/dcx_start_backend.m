function ok = dcx_start_backend(opts)
%DCX_START_BACKEND Start the DATACORE-X integration service (FastAPI) in
%   external-source mode, if it is not already answering on localhost:8000.
arguments
    opts.Root (1,1) string = fullfile(fileparts(fileparts(fileparts(mfilename('fullpath')))), 'app')
    opts.Port (1,1) double = 8000
end
url = sprintf('http://localhost:%d/api/diag', opts.Port);
ok = ping(url);
if ok, fprintf('Integration service already running on port %d\n', opts.Port); return; end
be = fullfile(opts.Root, 'datacore-x', 'backend');
py = fullfile(opts.Root, 'venv', 'Scripts', 'python.exe');
cmd = sprintf(['start "dcx-backend" /MIN cmd /c "cd /d "%s" && set DCX_SOURCE=external&& set DCX_OPCUA=1&& ' ...
    'set DCX_HISTORIAN=%s&& "%s" -m uvicorn datacorex.api:app --host 127.0.0.1 --port %d > "%s" 2>&1"'], ...
    be, fullfile(opts.Root, 'historian.sqlite'), py, opts.Port, fullfile(opts.Root, 'backend_log.txt'));
system(cmd);
for i = 1:40
    pause(0.5);
    if ping(url), ok = true; break; end
end
if ok, fprintf('Integration service started: http://localhost:%d\n', opts.Port);
else, warning('dcx:backend', 'Service did not start; see %s', fullfile(opts.Root, 'backend_log.txt')); end
end

function ok = ping(url)
try
    webread(url, weboptions('Timeout', 1)); ok = true;
catch
    ok = false;
end
end
