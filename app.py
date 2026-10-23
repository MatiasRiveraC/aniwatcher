import threading
import logging

from flask import Flask
from flask_sock import Sock

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

sock = Sock()


def create_app() -> Flask:
    app = Flask(__name__)
    sock.init_app(app)

    from routes.watchlist import bp as watchlist_bp
    from routes.downloads import bp as downloads_bp
    from routes.notifications import bp as notifications_bp
    from routes.system import bp as system_bp, setup_log_handler
    from routes.settings import bp as settings_bp
    from routes import ws as ws_routes

    app.register_blueprint(watchlist_bp)
    app.register_blueprint(downloads_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(system_bp)
    app.register_blueprint(settings_bp)
    ws_routes.register(sock)

    setup_log_handler()

    from services.poller import poll_loop
    from services.renamer import watch_completed_folder
    from services.qbittorrent import import_loop
    threading.Thread(target=poll_loop,              daemon=True).start()
    threading.Thread(target=watch_completed_folder, daemon=True).start()
    # Idles unless torrent_client is qbittorrent, so switching in the UI works.
    threading.Thread(target=import_loop,            daemon=True).start()

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
