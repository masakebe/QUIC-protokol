import asyncio
import pathlib
import os
from aioquic.asyncio.server import serve
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import (
    StreamDataReceived,
    StopSendingReceived,
    ConnectionTerminated,
    HandshakeCompleted,
    ProtocolNegotiated,
    StreamReset,
    DatagramFrameReceived,
    ConnectionIdIssued,
    ConnectionIdRetired,
)
from aioquic.asyncio.protocol import QuicConnectionProtocol


from aioquic.tls import SessionTicket

# Dictionary to store session tickets
session_ticket_store = {}


def save_session_ticket(ticket: SessionTicket):
    session_ticket_store["ticket"] = ticket


def get_session_ticket():
    return session_ticket_store.get("ticket")


HOST = "localhost"
PORT = 4433
CERT = "cert.pem"
KEY = "key.pem"


class LoggingServerProtocol(QuicConnectionProtocol):
    def connection_made(self, transport):
        super().connection_made(transport)
        print("[SERVER] Connection initiated", flush=True)

    def quic_event_received(self, event):
        if isinstance(event, HandshakeCompleted):
            print(
                "[SERVER] QUIC handshake completed. ALPN:",
                event.alpn_protocol,
                flush=True,
            )
        elif isinstance(event, ProtocolNegotiated):
            print("[SERVER] Protocol negotiated:", event.alpn_protocol, flush=True)
        elif isinstance(event, StreamDataReceived):
            data = event.data.decode()
            print(f"[SERVER] Received on stream {event.stream_id}: {data}", flush=True)
            response = f"Echoing: {data[::-1]}"
            self._quic.send_stream_data(
                event.stream_id, response.encode(), end_stream=False
            )
            self.transmit()
        elif isinstance(event, StreamReset):
            print(
                f"[SERVER] Stream {event.stream_id} was reset. Error code: {event.error_code}",
                flush=True,
            )
        elif isinstance(event, StopSendingReceived):
            print(
                f"[SERVER] Peer requested stop on stream {event.stream_id} with code {event.error_code}",
                flush=True,
            )
        elif isinstance(event, DatagramFrameReceived):
            print(f"[SERVER] Datagram received: {event.data.decode()}", flush=True)
        elif isinstance(event, ConnectionIdIssued):
            print(
                f"[SERVER] Connection ID issued: {event.connection_id.hex()}",
                flush=True,
            )
        elif isinstance(event, ConnectionIdRetired):
            print(
                f"[SERVER] Connection ID retired: {event.connection_id.hex()}",
                flush=True,
            )
        elif isinstance(event, ConnectionTerminated):
            print(
                f"[SERVER] Connection closed. Error code: {event.error_code}, Frame type: {event.frame_type}, Reason: {event.reason_phrase}",
                flush=True,
            )


async def run_server():
    config = QuicConfiguration(is_client=False)
    config.load_cert_chain(certfile=pathlib.Path(CERT), keyfile=pathlib.Path(KEY))
    config.max_datagram_frame_size = 65536  # 👈 Enable datagrams
    # Load existing session ticket if available
    session_ticket = get_session_ticket()
    if session_ticket:
        config.session_ticket = session_ticket
    config.alpn_protocols = ["echo"]
    config.secrets_log_file = open(os.environ["SSLKEYLOGFILE"], "a")

    print(f"[SERVER] Listening on {HOST}:{PORT}...", flush=True)
    server = await serve(
        host=HOST,
        port=PORT,
        configuration=config,
        create_protocol=LoggingServerProtocol,
        session_ticket_handler=save_session_ticket,
    )
    try:
        await asyncio.Future()  # Run forever
    finally:
        server.close()


if __name__ == "__main__":
    asyncio.run(run_server())
