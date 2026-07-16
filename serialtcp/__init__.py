import logging

__version__ = '2.4.0'

logging.getLogger(__name__).addHandler(logging.NullHandler())
logging.basicConfig(level=logging.WARNING)
