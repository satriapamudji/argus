"""SimHash implementation for near-duplicate detection.

SimHash is a locality-sensitive hashing technique that produces similar
hash values for similar documents. Two documents are considered near-duplicates
if the Hamming distance between their SimHash values is below a threshold.

References:
- Charikar, M. S. (2002). Similarity estimation techniques from rounding algorithms.
- "Detecting Near-Duplicates for Web Crawling" - Manku, Jain, Sarma (Google 2007)
"""

import hashlib
import re
from typing import Optional


def tokenize(text: str, ngram_size: int = 3) -> list[str]:
    """Tokenize text into character n-grams for SimHash.

    Uses character-level n-grams (trigrams by default) which are more robust
    to minor variations than word-level tokens.

    Args:
        text: Input text to tokenize.
        ngram_size: Size of character n-grams (default 3).

    Returns:
        List of n-gram tokens.
    """
    # Normalize: lowercase, remove extra whitespace
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)

    # Remove punctuation for more robust matching
    text = re.sub(r"[^\w\s]", "", text)

    if len(text) < ngram_size:
        return [text] if text else []

    # Generate character n-grams
    return [text[i : i + ngram_size] for i in range(len(text) - ngram_size + 1)]


def _hash_token(token: str) -> int:
    """Hash a token to a 64-bit integer.

    Uses MD5 and takes the first 8 bytes for a 64-bit hash.

    Args:
        token: Token string to hash.

    Returns:
        64-bit unsigned integer hash.
    """
    h = hashlib.md5(token.encode("utf-8")).digest()[:8]
    return int.from_bytes(h, byteorder="big", signed=False)


def compute_simhash(
    text: str,
    ngram_size: int = 3,
    weights: Optional[dict[str, float]] = None,
) -> int:
    """Compute 64-bit SimHash signature for text.

    The algorithm:
    1. Tokenize text into n-grams
    2. Hash each token to a 64-bit value
    3. For each bit position, sum +1 if bit is 1, -1 if bit is 0
    4. Final hash: bit i is 1 if sum[i] > 0, else 0

    Args:
        text: Input text to hash.
        ngram_size: Size of character n-grams (default 3).
        weights: Optional token weights (unused in basic implementation).

    Returns:
        64-bit SimHash signature as unsigned integer.
    """
    tokens = tokenize(text, ngram_size)

    if not tokens:
        return 0

    # Initialize bit counts (64 bits)
    bit_counts: list[float] = [0.0] * 64

    for token in tokens:
        token_hash = _hash_token(token)
        weight = weights.get(token, 1.0) if weights else 1.0

        # Update bit counts
        for i in range(64):
            if token_hash & (1 << i):
                bit_counts[i] += weight
            else:
                bit_counts[i] -= weight

    # Build final hash
    simhash = 0
    for i in range(64):
        if bit_counts[i] > 0:
            simhash |= 1 << i

    return simhash


def hamming_distance(hash1: int, hash2: int) -> int:
    """Compute Hamming distance between two 64-bit hashes.

    Hamming distance is the number of bit positions where the bits differ.

    Args:
        hash1: First 64-bit hash.
        hash2: Second 64-bit hash.

    Returns:
        Number of differing bits (0-64).
    """
    xor = hash1 ^ hash2
    return bin(xor).count("1")


def is_near_duplicate(
    hash1: int,
    hash2: int,
    threshold: int = 4,
) -> bool:
    """Check if two hashes represent near-duplicate content.

    Args:
        hash1: First SimHash.
        hash2: Second SimHash.
        threshold: Maximum Hamming distance for near-duplicates (default 4).

    Returns:
        True if documents are near-duplicates.
    """
    return hamming_distance(hash1, hash2) <= threshold
