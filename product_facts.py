PRODUCT_FACTS = """
SockLock is a subscription sock-pairing product: a tiny magnetic clip that holds
sock pairs together through the wash and the dryer.
First payment: $29. Shipments: quarterly.
"""

import re

ALLOWED_NUMBERS = set(re.findall(r"\d+", PRODUCT_FACTS))
