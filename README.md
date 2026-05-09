# 🦢 Gooseman

> **⚠️ Disclaimer:** The project is still in early beta and may be unstable and full of bugs.

Gooseman is a lightweight web dashboard for managing and monitoring a running GooseRelayVPN client on a local machine or LAN server.

It provides a simple control panel for starting and stopping the client, viewing real-time logs, tracking usage statistics, and editing SOCKS proxy configuration through a browser interface.

<img width="1080" height="4263" alt="Gooseman Screenshot from Chrome Android" src="https://github.com/user-attachments/assets/9f875599-d91e-43ce-abc5-35c4835d4f6a" />

---

## Features

- Start and stop the GooseRelayVPN client from a web UI
- Live log viewer with automatic updates
- Real-time session and traffic statistics
- Quota tracking
- Dashboard password authentication based on SOCKS5 proxy password 
- SOCKS5 configuration editor (host, port, optional username/password)
- Responsive design for desktop and mobile devices
- Lightweight FastAPI backend with no external dependencies beyond Python packages

---

## Keep in mind

- ~~The project is currently Linux only, and I'm too lazy to do anything for other platforms yet.~~
- It uses `tailwindcss` and `jsdelivr` CDNs, which are as of now, still blocked in Iran. You can start the server just fine without those being loaded, it'll just miss the fanciness, aesthetics and the graph as well. Although, the styles will most likely be cached in your browser once you load the site once.

---

## Architecture

Gooseman consists of two main parts:

- **Backend (FastAPI)**
  - Launches and manages the `goose-client` process
  - Reads and parses logs from stdout
  - Tracks runtime statistics and quota usage
  - Exposes a simple HTTP API for the dashboard

- **Frontend (Single-page HTML)**
  - Built with TailwindCSS via CDN
  - Connects to backend endpoints using JavaScript fetch API
  - Displays logs, stats, and controls in real time

---

## Requirements

- Python 3.9+
- FastAPI
- Uvicorn
- GooseRelayVPN 1.6 linux binary (`goose-client`) placed in the same directory
- `client_config.json` file in the project root

---

## Installation

1. Clone the repository:

```bash
git clone https://github.com/Aydiniyom/Gooseman.git
cd Gooseman
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Move your `client_config.json` and `goose-client` files inside the project folder, in the root directory.

---

## Running

Start the dashboard with:

```bash
uvicorn main:app --host 0.0.0.0 --port 5000
```

Then you can access it via the host machine by visiting the URL `http://localhost:5000` or via other devices by `http://<host-machine-ip>:5000`.

> If port `5000` fails to bind, simply give another random port that isn't likely to be prebound.

---

## Updating

Simply `cd` into the project directory and run `git pull`, and rerun the `uvicorn` command.

---

## Thank you...

[@Kianmhz](https://github.com/Kianmhz) for making the wonderful project [GooseRelayVPN](https://github.com/Kianmhz/GooseRelayVPN/tree/main).
