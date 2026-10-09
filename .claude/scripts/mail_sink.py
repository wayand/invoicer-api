"""Tiny local SMTP sink for UI testing: accepts any mail, prints it to stdout.

Usage: python mail_sink.py PORT  (stdlib only; binds 127.0.0.1)
Nothing is ever relayed, so no real email can leave the machine.
"""

import socketserver
import sys
from email import message_from_string, policy


class Handler(socketserver.StreamRequestHandler):
    def reply(self, line):
        self.wfile.write(line.encode() + b"\r\n")

    def handle(self):
        self.reply("220 mail-sink ready")
        for raw in self.rfile:
            cmd = raw.decode(errors="replace").strip()
            verb = cmd.upper()
            if verb.startswith(("EHLO", "HELO")):
                self.reply("250 mail-sink")
            elif verb == "DATA":
                self.reply("354 end with <CRLF>.<CRLF>")
                lines = []
                for part in self.rfile:
                    text = part.decode(errors="replace")
                    if text.rstrip("\r\n") == ".":
                        break
                    lines.append(text)
                self.show("".join(lines))
                self.reply("250 queued")
            elif verb == "QUIT":
                self.reply("221 bye")
                return
            else:  # MAIL FROM, RCPT TO, RSET, NOOP, ...
                self.reply("250 ok")

    def show(self, source):
        msg = message_from_string(source, policy=policy.default)
        body = msg.get_body(preferencelist=("plain", "html"))
        print("=== MAIL ===", flush=True)
        print(f"To: {msg['To']}\nSubject: {msg['Subject']}", flush=True)
        print(body.get_content() if body else source, flush=True)
        print("=== END MAIL ===", flush=True)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with Server(("127.0.0.1", int(sys.argv[1])), Handler) as server:
        server.serve_forever()
