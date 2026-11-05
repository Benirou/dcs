from pathlib import Path

LUA_DIR = Path(__file__).parent / "lua"


def bridge_lua() -> str:
    return (LUA_DIR / "latam_bridge.lua").read_text(encoding="utf-8")
