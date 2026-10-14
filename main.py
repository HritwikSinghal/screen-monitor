# This is a sample Python script.

# Press ⌃R to execute it or replace it with your code.
# Press Double ⇧ to search everywhere for classes, files, tool windows, actions, and settings.
import argparse
import logging

from src.process import start

logging.basicConfig(format='%(asctime)s: %(name)s: %(levelname)s: %(lineno)d: %(message)s')

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mute audio while a target image is off screen.")
    parser.add_argument(
        "--select",
        action="store_true",
        help="forget the remembered window/monitor and show the source picker again",
    )
    args = parser.parse_args()
    start(reselect=args.select)
