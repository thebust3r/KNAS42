"""Checks a .wgt's signatures the way the TV does (file fingerprints + RSA signatures). Fails the build if not."""
import base64, hashlib, re, sys, zipfile
from lxml import etree
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

NS = {"ds": "http://www.w3.org/2000/09/xmldsig#"}
z = zipfile.ZipFile(sys.argv[1])
bad = 0
for name in ("author-signature.xml", "signature1.xml"):
    doc = etree.fromstring(z.read(name))
    si = doc.find("ds:SignedInfo", NS)
    for ref in si.findall("ds:Reference", NS):
        uri = ref.get("URI")
        if uri.startswith("#"):
            continue
        want = base64.b64decode(re.sub(r"\s", "", ref.find("ds:DigestValue", NS).text))
        if hashlib.sha512(z.read(uri)).digest() != want:
            print(f"{name}: {uri} fingerprint doesn't match"); bad += 1
    sv = base64.b64decode(re.sub(r"\s", "", doc.find("ds:SignatureValue", NS).text))
    cert = x509.load_der_x509_certificate(base64.b64decode(re.sub(r"\s", "", doc.find(".//ds:X509Certificate", NS).text)))
    try:
        cert.public_key().verify(sv, etree.tostring(si, method="c14n", exclusive=True), padding.PKCS1v15(), hashes.SHA512())
        print(f"{name}: signature OK ({cert.subject.rfc4514_string()})")
    except Exception:
        print(f"{name}: SIGNATURE DOES NOT VERIFY ({cert.subject.rfc4514_string()})"); bad += 1
sys.exit(1 if bad else 0)
