"""Content hashing for incremental re-analysis (SRS 3.1, FR-4).

SRS 3.1 requires "a centralized paragraph-hashing framework (e.g., xxHash checks)
to ensure only modified sentences trigger full pipeline re-parsing", and FR-4
assigns the checks to the **Language Server** -- this repository. This module is
that hash.

Why blake2b from the standard library
-------------------------------------
The SRS names xxHash as an example ("e.g."), not a mandate. Three candidates were
measured over the 725 KB reference document, and the choice is not a performance
one -- every candidate is far below the noise floor of the analysis it guards:

===================  ==========  ==============================================
Candidate            Throughput  Why not
===================  ==========  ==============================================
``zlib.crc32``       2,432 MB/s  32-bit. Over a 5,885-sentence document the
                                 birthday bound gives a ~0.4% chance of a
                                 collision, and a collision here silently
                                 returns *the wrong sentence's analysis*.
``xxhash``           n/a         A third-party C extension. It would be the
                                 first runtime dependency added for a feature
                                 that stdlib already serves, against the
                                 discipline of ADR-006, and being
                                 non-cryptographic it would still need a
                                 collision policy.
``hashlib.blake2b``  472 MB/s    Chosen.
===================  ==========  ==============================================

At 16 bytes the digest is wide enough that collisions can be ignored rather than
handled, which removes an entire failure mode from the incremental path. The cost
is **0.7 microseconds per sentence** -- against roughly 780 microseconds to
analyse one, so under 0.1% of the work it saves. See ADR-016.

``hash()`` is deliberately not used: it is salted per process, so a daemon
restart would invalidate every cached analysis.
"""

from __future__ import annotations

import hashlib
from typing import Final

#: Digest width in bytes. 128 bits: at document scale the probability of a
#: collision is far below that of a hardware fault, so the incremental path does
#: not need a collision policy.
DIGEST_SIZE: Final = 16


def sentence_hash(text: str) -> str:
    """Return the stable content hash of one sentence.

    Stable across processes and across runs, which is what makes it usable as a
    cache key for a daemon that restarts.

    Args:
        text: The sentence exactly as it appears in the document.

    Returns:
        A 32-character lowercase hexadecimal digest.
    """
    return hashlib.blake2b(text.encode("utf-8"), digest_size=DIGEST_SIZE).hexdigest()


__all__ = ["DIGEST_SIZE", "sentence_hash"]
