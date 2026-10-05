"""Authoritative Host -> Hades backend command contract.

This module owns the public Hades module-protocol command interface. Resident
Lua commands remain a separate interface behind Hades2ResidentSession.
"""


class Hades2CommandContract:
    def __init__(self, adapter):
        self.adapter = adapter

    def dispatch(self, command, params, request_id):
        if command == "scan":
            return self.adapter.scan()
        raise ValueError("未知命令。")
