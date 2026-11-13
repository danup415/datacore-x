# Ignition 8.x project library script:  dcx.bridge   (Jython 2.7)
#
# REST route between the DATACORE-X integration service and Ignition, for
# installations that do not use the OPC UA route.  Import
# ignition/tags/datacorex_memory_tags.json into the tag provider first.
#
# Gateway Timer Event (fixed rate, 1000 ms):
#     dcx.bridge.poll_tags()
#
# Every write carries the snapshot seq into [DATACORE_X]System/Seq so screens
# and the historian can verify they show the same snapshot as the 3D twin.
#
# NOTE: written against the documented system.net.httpClient / system.tag
# APIs; not executed in the environment where this project was generated.

BASE = "http://localhost:8000"
PROVIDER = "[default]"
_client = system.net.httpClient(timeout=3000)
_log = system.util.getLogger("DCX.bridge")


def _p(path):
    # "[DATACORE_X]Cooling/P_01/flow_ls" -> "[default]DATACORE_X/Cooling/P_01/flow_ls"
    return PROVIDER + "DATACORE_X/" + path.split("]", 1)[1]


def poll_tags():
    try:
        r = _client.get(BASE + "/api/tags")
        if not r.good:
            raise Exception("HTTP %s" % r.statusCode)
        doc = r.json
        paths, values = [], []
        for path, rec in doc["tags"].items():
            paths.append(_p(path))
            values.append(rec["v"])
        system.tag.writeBlocking(paths, values)
        system.tag.writeBlocking([PROVIDER + "DATACORE_X/System/Last_Poll_OK"], [True])
    except Exception, e:
        _log.warn("DCX poll failed: %s" % e)
        system.tag.writeBlocking([PROVIDER + "DATACORE_X/System/Last_Poll_OK"], [False])


def _headers(role, user):
    return {"X-DCX-Role": role, "X-DCX-User": user, "Content-Type": "application/json"}


def send_command(command, asset=None, name=None, value=None, role="operator", user=None):
    """Returns the acknowledgement record (status RECEIVED/ACCEPTED/REJECTED;
    poll get_command(id) for EXECUTED confirmation)."""
    user = user or system.security.getUsername()
    body = {"command": command, "asset": asset, "name": name, "value": value}
    r = _client.post(BASE + "/api/commands", data=system.util.jsonEncode(body), headers=_headers(role, user))
    return r.json


def get_command(cmd_id):
    return _client.get(BASE + "/api/commands/" + cmd_id).json


def request_scenario(scenario_id, params=None, horizon_s=1800, role="operator", user=None):
    user = user or system.security.getUsername()
    body = {"scenario_id": scenario_id, "params": params or {}, "horizon_s": horizon_s}
    return _client.post(BASE + "/api/scenarios/requests", data=system.util.jsonEncode(body), headers=_headers(role, user)).json


def approve_scenario(request_id, role="operator", user=None):
    user = user or system.security.getUsername()
    return _client.post(BASE + "/api/scenarios/requests/%s/approve" % request_id, data="{}", headers=_headers(role, user)).json


def scenario_result(run_id):
    return _client.get(BASE + "/api/scenarios/runs/" + run_id).json


def ack_alarm(alarm_id, role="operator", user=None):
    user = user or system.security.getUsername()
    return _client.post(BASE + "/api/alarms/%s/ack" % alarm_id, data="{}", headers=_headers(role, user)).json
