# This is a sample Python script.

# Press ⌃R to execute it or replace it with your code.
# Press Double ⇧ to search everywhere for classes, files, tool windows, actions, and settings.
import logging

from src.process import start
from src.capture import Capture

logging.basicConfig(format='%(asctime)s: %(name)s: %(levelname)s: %(lineno)d: %(message)s')

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

if __name__ == "__main__":
    start()
    # logger.debug("Starting xdg")
    # client = Capture()
    # client.start()
