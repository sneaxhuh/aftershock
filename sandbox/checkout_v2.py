import os

os.environ["SERVICE_ROLE"] = "checkout"
os.environ["CHECKOUT_VERSION"] = "2"
from sandbox.service import main

main()
