import sys
import json
import subprocess
import tempfile
import os
import logging
from typing import Union, Dict, Any
from polycli.models import PriceSeries, MultiLineSeries

class ChartManager:
    _instance = None
    _current_process = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ChartManager, cls).__new__(cls)
        return cls._instance

    def start(self):
        pass

    def plot(self, data: Union[PriceSeries, MultiLineSeries], metadata: dict = None):
        """Spawn a new process to show the chart (legacy single-interval)"""

        payload = {
            "title": getattr(data, "title", "Market Price"),
            "traces": [],
            "metadata": metadata or {}
        }

        if isinstance(data, MultiLineSeries):
            payload["title"] = data.title
            for trace in data.traces:
                payload["traces"].append({
                    "x": trace.timestamps(),
                    "y": trace.prices(),
                    "name": trace.name,
                    "color": trace.color
                })
        elif isinstance(data, PriceSeries):
            if not data.points: return
            payload["title"] = data.name
            payload["traces"].append({
                "x": data.timestamps(),
                "y": data.prices(),
                "name": data.name,
                "color": data.color
            })

        self._launch_viewer(payload)

    def plot_intervals(
        self,
        title: str,
        interval_data: Dict[str, Dict[str, Any]],
        default_interval: str = "1d",
        metadata: dict = None
    ):
        """
        Spawn chart with pre-loaded data for all intervals.

        Args:
            title: Chart title
            interval_data: Dict mapping interval -> {"traces": [...]}
            default_interval: Which interval to show initially
            metadata: Additional metadata
        """
        payload = {
            "title": title,
            "intervals": interval_data,
            "default_interval": default_interval,
            "metadata": metadata or {}
        }

        self._launch_viewer(payload)

    def _launch_viewer(self, payload: dict):
        """Write payload to temp file and spawn viewer process"""
        # Write to temp file
        fd, path = tempfile.mkstemp(suffix=".json", prefix="polyfloat_chart_")
        with os.fdopen(fd, 'w') as f:
            json.dump(payload, f)

        # Kill previous window
        if self._current_process and self._current_process.poll() is None:
            try:
                self._current_process.terminate()
            except:
                pass

        # Spawn the viewer
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "charting.py"))
        cmd = [sys.executable, script_path, path]

        logging.debug(f"Launching chart command: {cmd}")

        try:
            self._current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            logging.error(f"Failed to launch chart viewer: {e}")
