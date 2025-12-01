import base64
from cryptography.fernet import Fernet

# ---------------------------
# MASTER KEY (use your actual key)
# ---------------------------
KEY = b"YOUR_FERNET_KEY_HERE"
cipher = Fernet(KEY)

# ---------------------------
# Decrypt a normal text field
# ---------------------------
def decrypt_text(enc_value):
    if not enc_value:
        return ""
    try:
        return cipher.decrypt(enc_value.encode()).decode()
    except:
        return ""

# ---------------------------
# Decrypt Base64 FILE string
# ---------------------------
def decrypt_file(enc_file_string):
    """
    enc_file_string will be a base64 encrypted string
    We must first decrypt → then decode base64 → return raw bytes
    """
    try:
        decrypted = cipher.decrypt(enc_file_string.encode()).decode()
        file_bytes = base64.b64decode(decrypted)
        return file_bytes
    except:
        return b""
