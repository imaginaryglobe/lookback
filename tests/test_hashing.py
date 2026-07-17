from hashing import path_to_hash_hex, path_to_id


def test_same_path_hashes_the_same():
    assert path_to_id(r"C:\Photos\img.jpg") == path_to_id(r"C:\Photos\img.jpg")


def test_different_paths_hash_differently():
    assert path_to_id(r"C:\Photos\img.jpg") != path_to_id(r"C:\Photos\img2.jpg")


def test_case_insensitive_on_windows():
    # Dedup relies on this: the same file reached via different casing must
    # still map to one Qdrant point id, or reindexing creates duplicates.
    assert path_to_id(r"C:\Photos\IMG.JPG") == path_to_id(r"c:\photos\img.jpg")


def test_normalizes_path_separators_and_dot_segments():
    assert path_to_id(r"C:\Photos\.\img.jpg") == path_to_id(r"C:\Photos\img.jpg")
    assert path_to_id(r"C:\Photos\sub\..\img.jpg") == path_to_id(r"C:\Photos\img.jpg")


def test_hash_hex_matches_id_derivation():
    # Both are derived from the same normalized sha256 digest -- the hex string
    # is just the full digest where the id is the first 8 bytes as an int.
    path = r"C:\Photos\img.jpg"
    digest_prefix = path_to_hash_hex(path)[:16]  # first 8 bytes as hex
    assert int(digest_prefix, 16) == path_to_id(path)


def test_hash_hex_is_deterministic_and_distinct():
    assert path_to_hash_hex(r"C:\Photos\a.jpg") == path_to_hash_hex(r"C:\Photos\a.jpg")
    assert path_to_hash_hex(r"C:\Photos\a.jpg") != path_to_hash_hex(r"C:\Photos\b.jpg")
