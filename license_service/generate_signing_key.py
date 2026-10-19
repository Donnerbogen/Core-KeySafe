import base64
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption
private = Ed25519PrivateKey.generate()
priv = private.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
pub = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
print("LICENSE_SIGNING_PRIVATE_KEY=" + base64.b64encode(priv).decode())
print("DESKTOP_PUBLIC_KEY=" + base64.b64encode(pub).decode())
print("IMPORTANT: Store PRIVATE key only as a Render secret. Never commit it.")
