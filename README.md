[توضیحات فارسی](https://github.com/Aydiniyom/Gooseman/blob/main/README-fa.md)

# 🦢 Gooseman

Gooseman is a lightweight web dashboard for managing and monitoring a running GooseRelayVPN client on a local machine or LAN server.

It provides a simple control panel for starting and stopping the client, viewing real-time logs, tracking usage statistics, and editing SOCKS proxy configuration through a browser interface.

<img width="919" height="1049" alt="Gooseman dashboard with tailwindcss and jsdelivr chart loaded" src="https://github.com/user-attachments/assets/a02ad391-07a6-41fe-83a8-4aab7d62f9f8" />

---

## Features

- A beautiful and aesthetic, pleasing-to-look-at dashboard.
- Supports both Windows and Linux binaries
- Start and stop the GooseRelayVPN client from a web UI
- Live log viewer with automatic updates
- Real-time session and traffic statistics
- Quota tracking
- Capable of stopping the client upon reaching a customizable quota limit
- Dashboard password authentication based on SOCKS5 proxy password 
- SOCKS5 configuration editor (host, port, optional username/password)
- Responsive design for desktop and mobile devices
- Lightweight FastAPI backend with no external dependencies beyond Python packages
- Extremely easy to install and setup

---

## Keep in mind

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
- GooseRelayVPN 1.6 binary (`goose-client(.exe)`) placed in the same directory
- `client_config.json` file in the project root

## Installation

1. [Get the latest release](https://github.com/Aydiniyom/Gooseman/releases/latest)

2. `cd` into the root directory of the project

> **Linux note:** You may need to create and activate a virtual environment before continuing:
>
> ```bash
> python -m venv .venv
> source .venv/bin/activate
> ```
>
> Run these commands from the root directory of the project.

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Move your `client_config.json` and `goose-client(.exe)` files inside the project folder, in the root directory

---

## Running

Start the dashboard with:

```bash
python run.py
```

Then you can access it via the host machine by visiting the URL `http://localhost:5000` or via other devices by `http://<host-machine-ip>:5000`.

---

## Updating

There has been a built-in update mechanism added to the dashboard itself.

---

## Thank you...

[@Kianmhz](https://github.com/Kianmhz) for making the wonderful project [GooseRelayVPN](https://github.com/Kianmhz/GooseRelayVPN/tree/main).

Everyone who decided to star the project. It means the world to me.