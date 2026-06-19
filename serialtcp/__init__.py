import logging

__version__ = '2.2.2'

logging.getLogger(__name__).addHandler(logging.NullHandler())
logging.basicConfig(level=logging.WARNING)
