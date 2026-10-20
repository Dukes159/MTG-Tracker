# MTG Tracker server install

This package runs MTG Tracker in Docker Compose with Gunicorn. It includes a snapshot of the current collection database, including the existing profiles, cards, and saved Card Kingdom prices. On first start, Docker initializes a persistent volume from that snapshot. Later rebuilds keep the volume and its data.

## Install on the server

1. Install Docker Engine with the Docker Compose plugin.
2. Extract the package into a directory on the server.
3. Copy `.env.example` to `.env`.
4. Set `MTG_TRACKER_SECRET_KEY` in `.env` to a unique random value. For example, on Linux run `openssl rand -hex 32` and paste the result into the file.
5. Start the app from the extracted directory:

   ```sh
   docker compose up -d --build
   ```

6. Open `http://SERVER-IP:9006` from a browser on the server's network. If port 9006 is already in use, set a different `MTG_TRACKER_PORT` in `.env` before starting.

The container needs outbound internet access for Scryfall card search/import and Card Kingdom price refreshes. Its SQLite database persists in the `mtg_tracker_data` Docker volume. Use `docker compose down` to stop it; do not use `docker compose down -v` unless you intend to delete the saved collection volume.

## Back up the database

Create a consistent SQLite backup inside the running container, then copy it beside the Compose file:

```sh
docker compose exec -T mtg-tracker python -c "import sqlite3; source=sqlite3.connect('/data/collection.db'); target=sqlite3.connect('/data/collection-backup.db'); source.backup(target); target.close(); source.close()"
docker compose cp mtg-tracker:/data/collection-backup.db ./collection-backup.db
```

## Network access

The app has profile selection, but profiles are not protected by individual logins. Keep it on a trusted network unless you put it behind an authenticated HTTPS reverse proxy. The built-in Gunicorn listener serves HTTP on the configured port.
