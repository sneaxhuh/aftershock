import os

os.environ["SERVICE_ROLE"] = "checkout"
os.environ["CHECKOUT_VERSION"] = "1"
from sandbox.service import main

main()
