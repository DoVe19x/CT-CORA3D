"""Petit client du serveur de contrôle de CADCraft (lignes JSON sur 127.0.0.1)."""
import json, socket, sys
from pathlib import Path
PORT = 47651
TOKEN = Path.home().joinpath(f".cache/cadcraft-control-{PORT}.token").read_text().strip()

class Client:
    def __init__(self, port=PORT):
        self.s = socket.create_connection(("127.0.0.1", port), timeout=120)
        self.f = self.s.makefile("rwb")
        self.n = 0
    def __call__(self, method, params=None):
        self.n += 1
        req = {"id": self.n, "method": method, "token": TOKEN}
        if params is not None:
            req["params"] = params
        self.f.write((json.dumps(req) + "\n").encode()); self.f.flush()
        rep = json.loads(self.f.readline())
        if "error" in rep:
            raise RuntimeError(f"{method}: {rep['error']}")
        return rep.get("result", rep)

if __name__ == "__main__":
    c = Client()
    method = sys.argv[1]
    params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else None
    print(json.dumps(c(method, params), ensure_ascii=False, indent=1))
