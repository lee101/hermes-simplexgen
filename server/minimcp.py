import inspect
import json
import sys
import typing

PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean"}


def _schema(annotation):
    if typing.get_origin(annotation) is list:
        return {"type": "array", "items": {"type": _TYPES.get(typing.get_args(annotation)[0], "string")}}
    return {"type": _TYPES.get(annotation, "string")}


class MiniMCP:
    def __init__(self, name, instructions=""):
        self.name = name
        self.instructions = instructions
        self.tools = {}

    def tool(self, read_only):
        def register(fn):
            sig = inspect.signature(fn)
            hints = typing.get_type_hints(fn)
            props, required = {}, []
            for pname, param in sig.parameters.items():
                props[pname] = _schema(hints.get(pname, str))
                if param.default is inspect.Parameter.empty:
                    required.append(pname)
            self.tools[fn.__name__] = {
                "fn": fn,
                "hints": hints,
                "def": {
                    "name": fn.__name__,
                    "description": inspect.getdoc(fn) or "",
                    "inputSchema": {"type": "object", "properties": props, "required": required},
                    "annotations": {"readOnlyHint": read_only, "destructiveHint": False, "openWorldHint": False},
                },
            }
            return fn

        return register

    def _call(self, params):
        tool = self.tools.get(params.get("name"))
        if tool is None:
            return {"content": [{"type": "text", "text": f"unknown tool {params.get('name')}"}], "isError": True}
        args = params.get("arguments") or {}
        sig = inspect.signature(tool["fn"])
        kwargs = {}
        try:
            for pname, param in sig.parameters.items():
                if pname not in args:
                    if param.default is inspect.Parameter.empty:
                        raise ValueError(f"missing argument {pname}")
                    continue
                want, val = tool["hints"].get(pname, str), args[pname]
                if want in (int, float) and isinstance(val, (int, float, str)) and not isinstance(val, bool):
                    val = want(val)
                elif want is bool and isinstance(val, str):
                    val = val.strip().lower() in ("1", "true", "yes")
                kwargs[pname] = val
            text = tool["fn"](**kwargs)
            err = False
            try:
                err = json.loads(text).get("ok") is False
            except Exception:
                pass
            return {"content": [{"type": "text", "text": text}], "isError": err}
        except Exception as e:
            return {"content": [{"type": "text", "text": json.dumps({"ok": False, "error": str(e)})}], "isError": True}

    def handle(self, msg):
        method, mid = msg.get("method"), msg.get("id")
        if mid is None:
            return None
        if method == "initialize":
            asked = (msg.get("params") or {}).get("protocolVersion")
            result = {
                "protocolVersion": asked if asked in PROTOCOLS else PROTOCOLS[0],
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": self.name, "version": "0.2.0"},
                "instructions": self.instructions,
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": [t["def"] for t in self.tools.values()]}
        elif method == "tools/call":
            result = self._call(msg.get("params") or {})
        else:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def run(self):
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                reply = self.handle(json.loads(line))
            except Exception as e:
                reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(e)}}
            if reply is not None:
                sys.stdout.write(json.dumps(reply) + "\n")
                sys.stdout.flush()
