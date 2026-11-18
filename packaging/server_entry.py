"""FBOSINT-Server.exe: backend + web dashboard for Local or Network mode.

No arguments -> 'serve'. Examples:
  FBOSINT-Server.exe                         (127.0.0.1:8765)
  FBOSINT-Server.exe serve --host 0.0.0.0    (network mode)
  FBOSINT-Server.exe create-admin admin
  FBOSINT-Server.exe backup | restore <zip> | gen-cert --ip 192.168.1.10
"""
import sys

from fbosint.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["serve"]))
