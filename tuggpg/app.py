import logging
import sys
from datetime import datetime

import gnupg
from flask import Flask, Response, render_template, request
from werkzeug.exceptions import abort
from werkzeug.middleware.proxy_fix import ProxyFix

# Simple logger
logger = logging.getLogger('tuggpg')
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setFormatter(formatter)
logger.addHandler(stdout_handler)
logger.propagate = False

app = Flask(__name__)
# Proxyfix
app.wsgi_app = ProxyFix(app.wsgi_app)

PATH = "/opt/flask-tuggpg/gnupg"
KEYRING = "keysigningparty"
GNUPG = gnupg.GPG(gnupghome=PATH, keyring=KEYRING + ".kbx")
GNUPG.encoding = "utf-8"
KEY_ORDER = {
    "keyid": 1,
    "algo": 2,
    "length": 3,
    "curve": 4,
    "date": 5,
    "expires": 6,
    "uids": 7,
    "sigs": 8,
    "fingerprint": 9,
}


@app.route("/", methods=["GET", "POST"])
def index():
    remote_user = request.headers.get("X_REMOTE_USER", "anonymous")
    remote_addr = request.headers.get("X_FORWARDED_FOR")

    current_time = datetime.now()

    public_keys = GNUPG.list_keys(sigs=True)
    filtered_keys = []
    desired_keys = ["fingerprint", "uids", "length", "curve", "keyid", "date", "expires", "sigs", "algo"]

    if request.method == "POST":
        if "BEGIN PGP PRIVATE KEY BLOCK" not in request.form.get("gpgkey"):
            newgpgkey = request.form.get("gpgkey")
            import_result = GNUPG.import_keys(newgpgkey)
            # Fallback to latin-1 encoding
            if import_result.count == 0 and GNUPG.encoding == "utf-8":
                GNUPG.encoding = "latin-1"
                print(GNUPG.encoding)
                import_result = GNUPG.import_keys(newgpgkey)

            if import_result.count > 0:
                logger.info(
                    f"Key upload from {remote_addr} (user: {remote_user}) - Imported {import_result.count} key(s). Fingerprints: {import_result.fingerprints}"
                )
            else:
                logger.warning(f"Failed key upload from {remote_addr} (user: {remote_user})")

    public_keys = GNUPG.list_keys(sigs=True)

    for gpgkey in public_keys:
        filtered_key = {k: v for k, v in gpgkey.items() if k in desired_keys}
        filtered_keys.append(filtered_key)

        # Map the current algorithms based on RFC 9580 OpenPGP (section 9.1)
        if "algo" in filtered_key:
            if filtered_key["algo"] == "1":
                filtered_key["algo"] = "RSA"
            elif filtered_key["algo"] == "17":
                filtered_key["algo"] = "DSA"
            elif filtered_key["algo"] == "19":
                filtered_key["algo"] = "ECDSA"
            elif filtered_key["algo"] == "20":
                filtered_key["algo"] = "Elgamal"
            elif filtered_key["algo"] == "22":
                filtered_key["algo"] = "EdDSA"
            elif filtered_key["algo"] == "27":
                filtered_key["algo"] = "Ed25519"
            else:
                filtered_key["algo"] = "Unknown"

        if "date" in filtered_key:
            filtered_key["date"] = datetime.fromtimestamp(int(filtered_key["date"]))

        if "expires" in filtered_key:
            present = datetime.now()
            if filtered_key["expires"] == "":
                filtered_key["expires"] = "unlimited"
            elif present > datetime.fromtimestamp(int(filtered_key["expires"])):
                filtered_key["expires"] = "expired"
            else:
                filtered_key["expires"] = datetime.fromtimestamp(int(filtered_key["expires"]))

        if "fingerprint" in filtered_key:
            filtered_key["fingerprint"] = space_out_text(filtered_key["fingerprint"], 4)

        if "sigs" in filtered_key:
            signatures = []
            for signature in filtered_key["sigs"]:
                if signature[0] == filtered_key["keyid"]:
                    continue
                else:
                    signatures.append({signature[0]: signature[1]})
            filtered_key["sigs"] = signatures
            sigkeyids = []
            for sigkeyid in signatures:
                for sigkey, sigvalue in sigkeyid.items():
                    sigkeyids.append(sigkey)
            filtered_key["sigs"] = sigkeyids

        if "uids" in filtered_key:
            for uid in filtered_key["uids"]:
                if public_keys.uid_map[uid]['trust'] == 'r':
                    filtered_key["uids"].remove(uid)

    sorted_keys = []
    for key_dict in filtered_keys:
        sorted_dict = dict(sorted(key_dict.items(), key=lambda x: KEY_ORDER.get(x[0], 999)))
        sorted_keys.append(sorted_dict)

    return render_template("index.html", gpg_keys=sorted_keys, remote_user=remote_user, current_time=current_time)


# "Old" keyring way of downloading keyring/individual keys
@app.route("/pubkeys", defaults={"keyid": None}, methods=["GET"])
@app.route("/pubkeys/<keyid>", methods=["GET"])
def fetch_keys(keyid=None):
    remote_user = request.headers.get("X_REMOTE_USER", "anonymous")
    remote_addr = request.headers.get("X_FORWARDED_FOR")

    if keyid is not None:
        ascii_armored_public_keys = GNUPG.export_keys(keyid)
        if "BEGIN PGP PUBLIC KEY BLOCK" in ascii_armored_public_keys:
            logger.info(f"Key download from {remote_addr} (user: {remote_user}) - KeyID: {keyid}")
            return Response(
                ascii_armored_public_keys,
                mimetype="text/plain",
                headers={"Content-disposition": "attachment; filename=" + keyid + ".pub"},
            )
        else:
            logger.warning(
                f"Failed key download attempt from {remote_addr} (user: {remote_user}) - KeyID: {keyid} not found"
            )
            return abort(404)
    else:
        logger.info(f"Full keyring download from {remote_addr} (user: {remote_user})")
        ascii_armored_public_keys = GNUPG.export_keys([])
        if "BEGIN PGP PUBLIC KEY BLOCK" in ascii_armored_public_keys:
            return Response(
                ascii_armored_public_keys,
                mimetype="text/plain",
                headers={"Content-disposition": "attachment; filename=" + KEYRING + ".pub"},
            )


# GitHub etc. way of listing gpg key via REST
@app.route("/user", defaults={"keyid": None}, methods=["GET"])
@app.route("/user/<uid>.gpg", methods=["GET"])
def fetch_user_key(uid=None):
    if uid is not None:
        ascii_armored_public_keys = GNUPG.export_keys(uid)
        if "BEGIN PGP PUBLIC KEY BLOCK" in ascii_armored_public_keys:
            return Response(
                ascii_armored_public_keys,
                mimetype="text/plain",
            )
        else:
            return abort(404)


def space_out_text(text: str, n: int) -> str:
    return " ".join(text[i : i + n] for i in range(0, len(text), n))


if __name__ == "__main__":
    app.run(port=5000, debug=True)
