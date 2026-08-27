"""
Cryptographic logic for Nokia GPON Home Gateway authentication.
Replicates the browser's crypto_page.js + sjcl.js behavior in Python.

Flow:
1. Generate random AES-128 key and IV (16 bytes each)
2. AES-CBC encrypt the plaintext payload (PKCS7 padded, matching SJCL behavior)
3. RSA encrypt the AES key info string: base64(aeskey) + ' ' + base64(iv)
4. Return: encrypted=1&ct=<base64url_of_aes_ciphertext>&ck=<base64url_escaped_rsa_ciphertext>
"""
import re
import os
import base64
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5, AES
from Crypto.Util.Padding import pad


def extract_pubkey(html_text):
    """Extracts RSA public key from any router HTML page."""
    pubkey_match = re.search(
        r'(-----BEGIN PUBLIC KEY-----.*?-----END PUBLIC KEY-----)',
        html_text, re.DOTALL
    )
    if not pubkey_match:
        return None
    pubkey = pubkey_match.group(1).replace('\\', '')
    lines = [l.strip() for l in pubkey.split('\n') if l.strip()]
    header = lines[0]
    footer = lines[-1]
    body = ''.join(lines[1:-1])
    return header + '\n' + body + '\n' + footer


def extract_login_params(html_text):
    """Extracts pubkey, nonce, and token from the router login page HTML."""
    pubkey = extract_pubkey(html_text)
    if not pubkey:
        raise ValueError("Could not find RSA public key in login page.")
    nonce_match = re.search(r'var nonce = "(.*?)";', html_text)
    token_match = re.search(r'var token\s*=\s*"(.*?)";', html_text)

    if not nonce_match:
        raise ValueError("Could not find nonce in login page.")
    if not token_match:
        raise ValueError("Could not find csrf token in login page.")

    return pubkey, nonce_match.group(1), token_match.group(1)


def base64url_escape(b64_str):
    """
    Matches crypto_page.base64url_escape:
    '+' -> '-', '/' -> '_', '=' -> '.'
    """
    return b64_str.replace('+', '-').replace('/', '_').replace('=', '.')


def sjcl_base64url_encode(data_bytes):
    """
    SJCL base64url encoding: standard base64 but with URL-safe replacements.
    sjcl.codec.base64url.fromBits uses: '+' -> '-', '/' -> '_', no padding '='
    """
    b64 = base64.b64encode(data_bytes).decode('utf-8')
    return b64.replace('+', '-').replace('/', '_').rstrip('=')


def aes_cbc_encrypt(plaintext_bytes, key_bytes, iv_bytes):
    """
    AES-CBC encrypt with PKCS7 padding (matches SJCL's CBC mode).
    SJCL internally pads to block boundary.
    """
    cipher = AES.new(key_bytes, AES.MODE_CBC, iv_bytes)
    padded = pad(plaintext_bytes, AES.block_size)
    return cipher.encrypt(padded)


def aes_cbc_decrypt(ciphertext_bytes, key_bytes, iv_bytes):
    """AES-CBC decrypt (for decrypting router responses)."""
    from Crypto.Util.Padding import unpad
    cipher = AES.new(key_bytes, AES.MODE_CBC, iv_bytes)
    decrypted = cipher.decrypt(ciphertext_bytes)
    return unpad(decrypted, AES.block_size)


def rsa_encrypt(pubkey_pem, plaintext_str):
    """
    RSA PKCS#1 v1.5 encrypt. JSEncrypt.encrypt() returns base64 string.
    """
    rsa_key = RSA.import_key(pubkey_pem)
    cipher = PKCS1_v1_5.new(rsa_key)
    encrypted = cipher.encrypt(plaintext_str.encode('utf-8'))
    return base64.b64encode(encrypted).decode('utf-8')


def encrypt_post_data(pubkey_pem, plaintext):
    """
    Replicates crypto_page.encrypt_post_data(pubkey, plaintext):
    1. Generate random AES key (4 words = 16 bytes) and IV (4 words = 16 bytes)
    2. AES-CBC encrypt the plaintext
    3. RSA encrypt the string: base64(aeskey) + ' ' + base64(iv)
    4. Return: 'encrypted=1&ct=<base64url(aes_ct)>&ck=<base64url_escape(rsa_ct)>'
    """
    # Generate random AES key and IV (sjcl.random.randomWords(4, 0) = 4 * 32-bit = 16 bytes)
    aes_key = os.urandom(16)
    aes_iv = os.urandom(16)

    # AES-CBC encrypt the plaintext
    ct = aes_cbc_encrypt(plaintext.encode('utf-8'), aes_key, aes_iv)

    # base64url encode the ciphertext (sjcl.codec.base64url.fromBits)
    ct_b64url = sjcl_base64url_encode(ct)

    # RSA encrypt the AES info string: base64(aeskey) + ' ' + base64(iv)
    aes_info = base64.b64encode(aes_key).decode('utf-8') + ' ' + base64.b64encode(aes_iv).decode('utf-8')
    ck_b64 = rsa_encrypt(pubkey_pem, aes_info)

    # base64url_escape the RSA ciphertext
    ck_escaped = base64url_escape(ck_b64)

    return f'encrypted=1&ct={ct_b64url}&ck={ck_escaped}', aes_key, aes_iv
