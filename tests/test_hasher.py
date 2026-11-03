import hashlib
import os

import pytest

from hasher import CHUNK_SIZE, find_empty_files, find_exact_duplicates, get_file_hash


def test_known_sha256_vectors(tmp_path):
    # FIPS 180-4 / NIST example values
    (tmp_path / "abc.txt").write_bytes(b"abc")
    (tmp_path / "empty.bin").write_bytes(b"")
    assert get_file_hash(tmp_path / "abc.txt") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert get_file_hash(tmp_path / "empty.bin") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert len(get_file_hash(tmp_path / "abc.txt")) == 64


@pytest.mark.parametrize("size", [1, CHUNK_SIZE - 1, CHUNK_SIZE, CHUNK_SIZE + 1, 3 * CHUNK_SIZE + 7])
def test_chunked_hash_equals_hashlib_on_chunk_boundaries(tmp_path, size):
    data = os.urandom(size)
    p = tmp_path / "f.bin"
    p.write_bytes(data)
    assert get_file_hash(p) == hashlib.sha256(data).hexdigest()


def test_renamed_copy_is_found_and_one_byte_change_is_not(tmp_path):
    (tmp_path / "a.bin").write_bytes(b"hello world" * 1000)
    (tmp_path / "renamed.bin").write_bytes(b"hello world" * 1000)
    (tmp_path / "changed.bin").write_bytes(b"hello world" * 999 + b"hello worlD")
    groups = find_exact_duplicates(str(tmp_path))
    assert len(groups) == 1
    assert {os.path.basename(p) for p in groups[0]} == {"a.bin", "renamed.bin"}


def test_size_prefilter_gives_same_result_as_hashing_everything(tmp_path):
    for i in range(6):
        (tmp_path / f"u{i}.bin").write_bytes(os.urandom(100 + i))          # unique sizes
    (tmp_path / "d1.bin").write_bytes(b"x" * 500)
    (tmp_path / "d2.bin").write_bytes(b"x" * 500)
    (tmp_path / "same_size_diff.bin").write_bytes(b"y" * 500)
    fast = find_exact_duplicates(str(tmp_path), size_prefilter=True)
    full = find_exact_duplicates(str(tmp_path), size_prefilter=False)
    assert sorted(map(sorted, fast)) == sorted(map(sorted, full))
    assert len(fast) == 1


def test_empty_files_are_not_duplicates_but_are_reported(tmp_path):
    (tmp_path / "e1.txt").write_bytes(b"")
    (tmp_path / "e2.txt").write_bytes(b"")
    assert find_exact_duplicates(str(tmp_path)) == []
    assert len(find_empty_files(str(tmp_path))) == 2


def test_unreadable_file_is_reported_not_fatal(tmp_path):
    (tmp_path / "a.bin").write_bytes(b"1")
    errors = []
    find_exact_duplicates(str(tmp_path), files=[str(tmp_path / "a.bin"), str(tmp_path / "missing.bin")], errors=errors)
    assert len(errors) == 1 and "missing.bin" in errors[0][0]


def test_subfolders_are_scanned(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.bin").write_bytes(b"same content")
    (tmp_path / "sub" / "b.bin").write_bytes(b"same content")
    assert len(find_exact_duplicates(str(tmp_path))) == 1
