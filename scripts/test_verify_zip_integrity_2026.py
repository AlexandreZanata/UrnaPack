#!/usr/bin/env python3
"""CRC sobre ZIPs sintéticos identificados, incluindo duplicatas e corrupção."""
from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile
import hashlib
import json

from validate import load_limits
from verify_zip_integrity_2026 import check_zip, verify_item
from acquire_2026 import hashes, write_json, relative_url

REPO = Path(__file__).resolve().parents[1]
BODY = (REPO/"tests/fixtures/audit-2026/synthetic.csv").read_bytes()
LIMITS = load_limits(REPO)


class IntegrityTests(unittest.TestCase):
    def test_cached_crc_requires_new_source_hash_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); url="https://cdn.tse.jus.br/synthetic-integrity.zip"
            item={"url":url,"path":relative_url(url)};path=root/item["path"];path.parent.mkdir(parents=True)
            body=(REPO/"tests/fixtures/audit-2026/logs-synthetic.zip").read_bytes();path.write_bytes(body)
            write_json(path.with_name(path.name+".receipt.json"),dict(hashes(path,LIMITS["IO_BUFFER_BYTES"]),url=url,status="synthetic-fixture-not-download"))
            key=hashlib.sha256(Path(__file__).read_bytes()).hexdigest();cache=root/"cache";cache.mkdir()
            first=verify_item(item,root,cache,LIMITS,key);self.assertEqual(first["status"],"verified")
            second=verify_item(item,root,cache,LIMITS,key);self.assertEqual(second["status"],"reused_crc_after_source_rehash")
            path.write_bytes(body[:-1]+bytes([body[-1]^1]))
            changed=verify_item(item,root,cache,LIMITS,key);self.assertEqual(changed["status"],"error")
            self.assertIn("diverge do recibo",changed["error"])

    def test_each_duplicate_member_is_actually_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"synthetic-duplicates.zip"
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(path,"w",compression=zipfile.ZIP_STORED) as archive:
                    archive.writestr("synthetic.csv",BODY)
                    archive.writestr("synthetic.csv",BODY[:-1])
            result = check_zip(path,LIMITS)
            self.assertEqual(result["members_crc_checked"],2)
            self.assertEqual(result["duplicate_name_occurrences_preserved"],1)
            self.assertEqual(result["member_bytes_read"],2*len(BODY)-1)

    def test_corrupt_member_crc_and_expansion_limit_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"synthetic-corrupt.zip"
            with zipfile.ZipFile(path,"w",compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("synthetic.csv",BODY)
            with self.assertRaisesRegex(ValueError,"expansão"):
                check_zip(path,dict(LIMITS,MAX_AUDIT_ZIP_EXPANDED_BYTES=len(BODY)-1))
            with zipfile.ZipFile(path) as archive:
                info=archive.infolist()[0]
            data=bytearray(path.read_bytes());offset=info.header_offset+30+len(info.filename.encode())+len(info.extra)
            data[offset]^=1;path.write_bytes(data)
            with self.assertRaisesRegex(ValueError,"CRC"):
                check_zip(path,LIMITS)


if __name__ == "__main__":
    unittest.main()
