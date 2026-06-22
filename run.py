"""Flask application entry point."""

import os
from app import create_app
from app.config import config_map

env = os.environ.get("FLASK_ENV", "development")
config_class = config_map.get(env, config_map["default"])

app = create_app(config_class)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
