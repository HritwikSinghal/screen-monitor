# This is a sample Python script.

# Press ⌃R to execute it or replace it with your code.
# Press Double ⇧ to search everywhere for classes, files, tool windows, actions, and settings.
import argparse
import faulthandler
import logging
import signal

from src.process import start

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mute audio while a target image is off screen.")
    parser.add_argument(
        "--select",
        action="store_true",
        help="forget the remembered window/monitor and show the source picker again",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="debug logging (pipeline state changes, capture throughput every 60s)",
    )
    args = parser.parse_args()

    # Level is set on the root logger so every src.* module follows it; per-module
    # levels previously left src.capture stuck at WARNING.
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s: %(name)s: %(levelname)s: %(lineno)d: %(message)s",
    )
    # GStreamer, PipeWire and OpenCV are native code: dump the Python stack on
    # a segfault/abort, and on demand (`kill -USR1 <pid>`) to see where a hang is.
    faulthandler.enable()
    faulthandler.register(signal.SIGUSR1, all_threads=True)
    start(reselect=args.select)
