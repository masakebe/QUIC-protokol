# QUIC - start

run the following commands:

```bash
tshark -i 6 -f "udp port 4433" -w quic.pcap
```

```bash
python server.py
```

```bash
python client.py
```
