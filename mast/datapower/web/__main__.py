from mast.logging import make_logger
from gui import main

logger = make_logger("mast.datapower.web")
logger.info("Attempting to start web gui.")
main()
logger.info("web gui stopped")
