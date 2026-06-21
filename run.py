import os
from app import create_app

app = create_app()

# Railway injects PORT; fallback to 5000 for local dev
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # Bind to 0.0.0.0 so Railway can route traffic in
    app.run(host="0.0.0.0", port=port, debug=False)