"""OPC UA server exposing the registry namespace (L3 -> Ignition OPC UA client).

Node ids are ``ns=<idx>;s=DCX.<ASSET>.<key>`` exactly as listed in the
registry (``opc_node``), so the generated Ignition tag export binds without
manual mapping.  Values are written from the same sequenced snapshot as every
other consumer; ``DCX.System.Seq`` lets Ignition verify alignment.
Supervisory writes are deliberately *not* accepted over OPC UA in this
prototype — commands go through the acknowledged REST command path so role
checks and interlocks stay in one place.
"""
from __future__ import annotations

import asyncio

from asyncua import Server, ua

from .registry import assets, registry_document

SYS_STRINGS = ("SimClock", "Source", "Comm_plant", "Comm_ai", "Comm_historian", "Comm_opcua")


class OpcUaPublisher:
    def __init__(self, endpoint: str = "opc.tcp://0.0.0.0:4840/datacorex/"):
        self.endpoint = endpoint
        self.server = Server()
        self.nodes: dict[tuple[str, str], object] = {}
        self.loop = None
        self.ns = None

    async def start(self):
        await self.server.init()
        self.server.set_endpoint(self.endpoint)
        self.server.set_server_name("DATACORE-X Digital Twin")
        self.ns = await self.server.register_namespace("urn:datacorex:twin")
        objs = self.server.nodes.objects
        root = await objs.add_folder(ua.NodeId("DCX", self.ns), "DATACORE_X")
        for a in assets():
            if not a["tags"]:
                continue
            fold = await root.add_folder(ua.NodeId(f"DCX.{a['id']}", self.ns), a["id"])
            st = await fold.add_variable(ua.NodeId(f"DCX.{a['id']}.state", self.ns), "state", "UNKNOWN")
            self.nodes[(a["id"], "state")] = st
            for tg in a["tags"]:
                var = await fold.add_variable(ua.NodeId(f"DCX.{a['id']}.{tg['key']}", self.ns), tg["key"], 0.0,
                                              varianttype=ua.VariantType.Double)
                self.nodes[(a["id"], tg["key"])] = var
        sysf = await root.add_folder(ua.NodeId("DCX.System", self.ns), "System")
        self.nodes[("System", "Seq")] = await sysf.add_variable(ua.NodeId("DCX.System.Seq", self.ns), "Seq", 0,
                                                                 varianttype=ua.VariantType.Int64)
        self.nodes[("System", "SimTime")] = await sysf.add_variable(ua.NodeId("DCX.System.SimTime", self.ns), "SimTime", 0.0)
        for k in SYS_STRINGS:
            self.nodes[("System", k)] = await sysf.add_variable(ua.NodeId(f"DCX.System.{k}", self.ns), k, "",
                                                                 varianttype=ua.VariantType.String)
        self.nodes[("System", "LastPollOK")] = await sysf.add_variable(ua.NodeId("DCX.System.LastPollOK", self.ns),
                                                                        "LastPollOK", False, varianttype=ua.VariantType.Boolean)
        # facility-level KPIs (IT load, facility power, PUE, ...) as DCX.Facility.<key>
        facf = await root.add_folder(ua.NodeId("DCX.Facility", self.ns), "Facility")
        for t in registry_document()["facility_tags"]:
            self.nodes[("Facility", t["key"])] = await facf.add_variable(
                ua.NodeId(f"DCX.Facility.{t['key']}", self.ns), t["key"], 0.0, varianttype=ua.VariantType.Double)
        await self.server.start()
        self.loop = asyncio.get_running_loop()

    async def _write(self, snap):
        for aid, a in snap["assets"].items():
            n = self.nodes.get((aid, "state"))
            if n is not None:
                await n.write_value(a["state"])
            q = a.get("q", {})
            for k, v in a["v"].items():
                node = self.nodes.get((aid, k))
                if node is None:
                    continue
                if v is None or q.get(k) == "BAD":
                    dv = ua.DataValue(ua.Variant(0.0, ua.VariantType.Double), StatusCode_=ua.StatusCode(ua.StatusCodes.BadSensorFailure))
                    await node.write_value(dv)
                else:
                    await node.write_value(float(v), ua.VariantType.Double)
        await self.nodes[("System", "Seq")].write_value(int(snap["seq"]), ua.VariantType.Int64)
        await self.nodes[("System", "SimTime")].write_value(float(snap["sim_time_s"]))
        sysv = {"SimClock": snap.get("sim_clock", ""), "Source": (snap.get("source") or {}).get("type", ""),
                **{f"Comm_{k}": str(v) for k, v in (snap.get("comm") or {}).items()}}
        for k in SYS_STRINGS:
            await self.nodes[("System", k)].write_value(str(sysv.get(k, "")), ua.VariantType.String)
        await self.nodes[("System", "LastPollOK")].write_value(True, ua.VariantType.Boolean)
        for k, v in (snap.get("facility") or {}).items():
            node = self.nodes.get(("Facility", k))
            if node is not None and isinstance(v, (int, float)):
                await node.write_value(float(v), ua.VariantType.Double)

    def publish(self, snap):
        if self.loop is None:
            return
        asyncio.run_coroutine_threadsafe(self._write(snap), self.loop)

    async def stop(self):
        await self.server.stop()
