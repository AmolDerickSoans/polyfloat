import sys
import json
import argparse
import time
import asyncio
from pywry import PyWry
import os

class ChartViewer:
    def __init__(self):
        self.handler = PyWry()
        self.handler.daemon = True
        
    async def run_async(self, data_file: str):
        print(f"Reading data from {data_file}...")
        try:
            with open(data_file, 'r') as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error reading data: {e}")
            return

        # Load Template
        template_path = os.path.join(os.path.dirname(__file__), "template.html")
        try:
            with open(template_path, 'r') as f:
                template = f.read()
        except Exception as e:
            print(f"Error reading template: {e}")
            return

        # Inject Data
        full_html = template.replace("{{DATA}}", json.dumps(data))

        # Pass arguments individually
        self.handler.send_html(
            html=full_html,
            title=data.get("title", "PolyFloat Chart"),
            width=1000,
            height=600
        )
        
        print("Starting PyWry loop...")
        try:
            self.handler.start()
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("Exiting...")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("data_file", help="Path to JSON data file")
    args = parser.parse_args()
    
    viewer = ChartViewer()
    asyncio.run(viewer.run_async(args.data_file))