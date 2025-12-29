import sys
import json
import argparse
import os
import atexit
import signal
import time
from pywry import PyWry


class ChartViewer:
    def __init__(self):
        self.handler = PyWry()
        self.handler.daemon = True  # CRITICAL: Run in background thread
        self.data_file = None
        self._running = True

    def run(self, data_file: str):
        self.data_file = data_file

        try:
            with open(data_file, 'r') as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error reading data: {e}", file=sys.stderr)
            return

        # Load Template
        template_path = os.path.join(os.path.dirname(__file__), "template.html")
        try:
            with open(template_path, 'r') as f:
                template = f.read()
        except Exception as e:
            print(f"Error reading template: {e}", file=sys.stderr)
            return

        # Inject Data
        full_html = template.replace("{{DATA}}", json.dumps(data))

        # Register cleanup handlers
        atexit.register(self.cleanup)
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        # Send HTML to PyWry
        self.handler.send_html(
            html=full_html,
            title=data.get("title", "PolyFloat Chart")[:80],
            width=1000,
            height=650
        )

        # Start PyWry in daemon thread
        self.handler.start()

        # Keep process alive while window is open
        # PyWry daemon thread will keep running until window closes
        try:
            while self._running:
                # Check if the PyWry thread is still alive
                if hasattr(self.handler, '_thread') and self.handler._thread is not None:
                    if not self.handler._thread.is_alive():
                        break
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass

        self.cleanup()

    def _signal_handler(self, signum, frame):
        """Handle termination signals"""
        self._running = False

    def cleanup(self):
        """Cleanup temp file"""
        self._running = False
        if self.data_file and os.path.exists(self.data_file):
            try:
                os.remove(self.data_file)
            except:
                pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("data_file", help="Path to JSON data file")
    args = parser.parse_args()

    viewer = ChartViewer()
    viewer.run(args.data_file)
