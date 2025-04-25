# === CLIENT ===
import asyncio
import os
from aioquic.asyncio.client import connect
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import (
    StreamDataReceived,
    HandshakeCompleted,
    ConnectionTerminated,
    PingAcknowledged,
    ProtocolNegotiated,
    StreamReset,
    StopSendingReceived,
    DatagramFrameReceived,
    ConnectionIdIssued,
    ConnectionIdRetired,
)
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.tls import SessionTicket

# Store session ticket to enable 0-RTT
session_ticket_store = {}


def save_session_ticket(ticket: SessionTicket):
    session_ticket_store["ticket"] = ticket


class LoggingClientProtocol(QuicConnectionProtocol):
    def connection_made(self, transport):
        super().connection_made(transport)
        print("[CLIENT] Connection initiated", flush=True)

    def quic_event_received(self, event):
        if isinstance(event, HandshakeCompleted):
            print(
                "[CLIENT] QUIC handshake completed. ALPN:",
                event.alpn_protocol,
                flush=True,
            )
        elif isinstance(event, ProtocolNegotiated):
            print("[CLIENT] Protocol negotiated:", event.alpn_protocol, flush=True)
        elif isinstance(event, PingAcknowledged):
            print(f"[CLIENT] PING acknowledged", flush=True)
        elif isinstance(event, StreamDataReceived):
            print(
                f"[CLIENT] Received from stream {event.stream_id}: {event.data.decode()}",
                flush=True,
            )
        elif isinstance(event, StreamReset):
            print(
                f"[CLIENT] Stream {event.stream_id} was reset. Error code: {event.error_code}",
                flush=True,
            )
        elif isinstance(event, StopSendingReceived):
            print(
                f"[CLIENT] Received STOP_SENDING on stream {event.stream_id} with code {event.error_code}",
                flush=True,
            )
        elif isinstance(event, DatagramFrameReceived):
            print(f"[CLIENT] Datagram received: {event.data.decode()}", flush=True)
        elif isinstance(event, ConnectionIdIssued):
            print(
                f"[CLIENT] Connection ID issued: {event.connection_id.hex()}",
                flush=True,
            )
        elif isinstance(event, ConnectionIdRetired):
            print(
                f"[CLIENT] Connection ID retired: {event.connection_id.hex()}",
                flush=True,
            )
        elif isinstance(event, ConnectionTerminated):
            print(
                f"[CLIENT] Connection closed. Error code: {event.error_code}, Frame type: {event.frame_type}, Reason: {event.reason_phrase}",
                flush=True,
            )


async def run_client():
    config = QuicConfiguration(is_client=True)
    config.verify_mode = False
    config.alpn_protocols = ["echo"]
    config.max_datagram_frame_size = 65536

    # Load the session ticket if available
    if "ticket" in session_ticket_store:
        config.session_ticket = session_ticket_store["ticket"]

    ssl_key_log_file = None
    if "SSLKEYLOGFILE" in os.environ:
        ssl_key_log_file = open(os.environ["SSLKEYLOGFILE"], "a")
        config.secrets_log_file = ssl_key_log_file

    async with connect(
        "localhost",
        4433,
        configuration=config,
        create_protocol=LoggingClientProtocol,
        session_ticket_handler=save_session_ticket,
        wait_connected=False,
    ) as client:
        print("[CLIENT] Connected to server at localhost:4433", flush=True)
        # client.transmit()  # Handshake initial
        # await asyncio.sleep(2)  # Wait for the server to respond
        # STREAM events concurrently
        stream_ids = [0, 4]
        for i in range(2):
            for id in stream_ids:
                message = f"Hello QUIC {i} on stream {id}"
                print(f"[CLIENT] Sending: {message}", flush=True)
                client._quic.send_stream_data(id, message.encode(), end_stream=False)
                client.transmit()
            await asyncio.sleep(1)

        # # STREAM_RESET event
        for sid in stream_ids:
            print(f"[CLIENT] Resetting stream {sid}", flush=True)
            client._quic.reset_stream(stream_id=sid, error_code=42)
        await asyncio.sleep(2)

        # Attempting to send on a reset stream would raise an error, so skip that

        # DATAGRAM event
        if config.max_datagram_frame_size is not None:
            datagram = "Hello Datagram".encode()
            print(f"[CLIENT] Sending datagram: {datagram.decode()}", flush=True)
            client._quic.send_datagram_frame(datagram)
            client.transmit()
            await asyncio.sleep(2)

        # CONNECTION_ID event
        client.change_connection_id()
        client.transmit()
        await asyncio.sleep(2)

        # PING
        await client.ping()
        client.transmit()
        await asyncio.sleep(2)

        print("[CLIENT] Closing connection", flush=True)
        client.close(error_code=0, reason_phrase="Client is shutting down")
        await client.wait_closed()
        print("[CLIENT] Connection closed", flush=True)

    if ssl_key_log_file:
        ssl_key_log_file.close()


if __name__ == "__main__":
    asyncio.run(run_client())
    asyncio.run(run_client())  # second run uses cached session for 0-RTT
