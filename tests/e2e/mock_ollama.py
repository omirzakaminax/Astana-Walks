"""FAKE Ollama for browser checks only (no real model). Selection prompts get P1..P3; explain prompts
get every P-id. It answers in the requested language with fixed generic sentences and records whether
the app sent a JSON Schema (structured outputs). Run: python tests/e2e/mock_ollama.py [port]
Then start the server with OLLAMA_URL=http://127.0.0.1:<port> and OLLAMA_MODEL=qwen3:4b-instruct."""
import json, re, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
TXT = {"Russian": ("Рядом и укладывается в ваше время.", "Пройдитесь вокруг и сделайте фото."),
       "Kazakh": ("Жақын әрі уақытыңызға сыяды.", "Айналып жүріп, сурет түсіріңіз."),
       "English": ("Close by and fits your time.", "Walk around and take a photo.")}
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        d=json.dumps({"models":[{"name":"qwen3:4b-instruct"}]}).encode(); self.send_response(200); self.end_headers(); self.wfile.write(d)
    def do_POST(self):
        b=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        sysm, user = b["messages"][0]["content"], b["messages"][1]["content"]
        H.formats.append("schema" if isinstance(b.get("format"), dict) else str(b.get("format")))
        lang = next((k for k in TXT if f"in {k}" in sysm), "English")
        ids = re.findall(r'"id":\s*"(P\d+)"', user)
        if "already chosen" not in sysm: ids = ids[:3]
        why, act = TXT[lang]
        time.sleep(0.3)
        c = json.dumps({"recommendations":[{"id":i,"why":why,"activity":act,"visit_minutes":20} for i in ids],"note":""}, ensure_ascii=False)
        d = json.dumps({"message":{"content":c}}).encode(); self.send_response(200); self.end_headers(); self.wfile.write(d)
    def log_message(self,*a): pass
H.formats = []
if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 11999), H).serve_forever()
