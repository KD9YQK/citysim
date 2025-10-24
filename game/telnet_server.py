import asyncio
import socket
import traceback

from .commands import dispatch_command
from .models import ensure_player
from game.utility.messaging import clients, clients_lock
from game.utility.utils import load_config
from .world import main_loop
from game.utility.lore import get_random_lore
from game.utility.utils import validate_player_name


config = load_config()
ip_counts = {}
ip_counts_lock = asyncio.Lock()


class ClientSession:
    def __init__(self, reader, writer, addr):
        self.reader = reader
        self.writer = writer
        self.addr = addr
        self.name = None
        self.active = True
        # apply keepalive if socket available
        try:
            sock = writer.get_extra_info('socket')
            if sock is not None:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except Exception:
            pass

    async def send(self, msg: str, end='\r\n'):
        if not self.active:
            return
        try:
            if not msg.endswith('\r\n'):
                out = msg + end
            else:
                out = msg
            self.writer.write(out.encode(errors='ignore'))
            await self.writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            self.active = False
        except Exception as e:
            print(f"[ERROR] Failed to send to {self.name}: {e}")
            self.active = False


async def register_client(writer):
    peer = writer.get_extra_info('peername')
    ip = peer[0] if peer else 'unknown'
    async with ip_counts_lock:
        cnt = ip_counts.get(ip, 0) + 1
        ip_counts[ip] = cnt
    return ip


async def unregister_client(writer):
    peer = writer.get_extra_info('peername')
    ip = peer[0] if peer else 'unknown'
    async with ip_counts_lock:
        cnt = ip_counts.get(ip, 1) - 1
        if cnt <= 0:
            ip_counts.pop(ip, None)
        else:
            ip_counts[ip] = cnt


async def handle_client(reader, writer):
    peer = writer.get_extra_info('peername')
    addr = f"{peer[0]}:{peer[1]}" if peer else 'unknown'
    ip = await register_client(writer)

    # Check limits
    async with clients_lock:
        if len(clients) >= config.get('max_total_connections', 100):
            writer.write(b"Server busy. Try again later.\r\n")
            await writer.drain()
            await unregister_client(writer)
            writer.close()
            return
        async with ip_counts_lock:
            if ip and ip_counts.get(ip, 0) > config.get('max_connections_per_ip', 4):
                writer.write(b"Too many connections from your IP.\r\n")
                await writer.drain()
                await unregister_client(writer)
                writer.close()
                return

        session = ClientSession(reader, writer, addr)
        clients.add(session)

    print(f"[CONNECT] {addr} connected")

    try:
        # Send banner with CRLF (PuTTY safe)
        writer.write(b"\r\nWelcome to CitySim!\r\n")
        login_lore: str = f"    {get_random_lore()}\r\n\r\n"
        writer.write(login_lore.encode())
        writer.write(b"Enter your name: ")
        await writer.drain()

        # Read input with cleanup
        raw = await reader.readline()
        if not raw:
            return

        # Strip telnet control bytes
        # --- Clean up PuTTY/Telnet noise ---
        # Keep printable bytes and basic whitespace
        cleaned = bytes(b for b in raw if 32 <= b <= 126 or b in (9, 10, 13))

        # Remove Telnet IAC (0xFF) and stray single/double quotes PuTTY may send
        for bad in (b'\xff', b"'", b'"', b'\x00'):
            cleaned = cleaned.replace(bad, b'')

        # Decode safely
        name = cleaned.decode(errors='ignore').strip()

        # Validate and normalize using shared utility
        from game.utility.db import Database
        db = Database.instance()
        name_lower = name.lower()
        existing = db.execute(
            "SELECT name FROM players WHERE LOWER(name)=?",
            (name_lower,),
            fetchone=True
        )

        if existing:
            # Player already exists — treat as login, not creation
            session.name = existing["name"]  # preserve original capitalization
        else:
            # Validate and create new player
            try:
                session.name = validate_player_name(name)
            except ValueError as e:
                writer.write(f"Invalid name: {e}\r\n".encode())
                await writer.drain()
                return

        # Create or ensure player exists in DB
        ensure_player(session.name)

        await session.send(f"\r\nHello {session.name}! Type 'help' for commands.\r\n")

        while session.active:
            await session.send("> ", end="")  # same-line prompt
            data = await reader.readline()
            if not data:
                break

            cmd = data.decode(errors='ignore').strip().replace('\r', '').replace('\n', '')
            if not cmd:
                continue

            try:
                resp = await dispatch_command(session.name, cmd)
            except Exception as e:
                traceback.print_exc()
                resp = f"Error handling command: {e}"

            if resp == "__QUIT__":
                await session.send("Goodbye!\r\n")
                break

            await session.send(resp + "\r\n")

    except Exception as e:
        print(f"[ERROR] Client {addr}: {e}")
        traceback.print_exc()

    finally:
        async with clients_lock:
            clients.discard(session)
        await unregister_client(writer)
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
        print(f"[DISCONNECT] {addr} closed connection")


async def start_server(cfg):
    port = cfg.get('telnet_port', 8023)
    server = await asyncio.start_server(handle_client, '0.0.0.0', port, limit=8192)
    print(f"CitySim Hardened Telnet server running on port {port}...\nUse PuTTY (raw or telnet mode) or telnet client.")
    # start NPC loop in background
    asyncio.create_task(main_loop())
    async with server:
        await server.serve_forever()
