"""Public key that signs the releases' SHA256SUMS.txt (Ed25519, hex).

Written by ``tools/make_update_key.py``; the matching private key is the
``UPDATE_SIGNING_KEY`` secret of the GitHub repository (release workflow).
Empty: this build cannot verify a release, so it does not update itself.
"""
PUBLIC_KEY = '9243f0296f87615df9f15e10ddc8acd0db7a2b482457d41f97f4088231afa6e2'
