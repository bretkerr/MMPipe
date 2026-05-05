#!/usr/bin/env python3
"""
Tests for mm.py — covers UMPP framing (emit), protocol parsing, magic-byte
fallback, and the mock AI path of analyze_vision.
"""

import io
import os
import sys
import json
import base64
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# Minimal 1×1 PNG (valid binary image)
_PNG_1x1 = (
    b'\x89PNG\r\n\x1a\n'
    b'\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
    b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx'
    b'\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N'
    b'\x00\x00\x00\x00IEND\xaeB`\x82'
)

# Minimal JPEG SOI marker
_JPEG_STUB = b'\xff\xd8\xff\xe0' + b'\x00' * 20

PROTOCOL_MAGIC = b"MMP/1.0\n"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_temp_image(suffix='.png', data=_PNG_1x1):
    """Write data to a temp file and return its path."""
    f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    f.write(data)
    f.close()
    return f.name


def capture_emit(file_path):
    """Run emit() and return the raw bytes written to stdout."""
    buf = io.BytesIO()
    with patch('sys.stdout') as mock_stdout:
        mock_stdout.buffer = buf
        from mm import emit
        emit(file_path)
    return buf.getvalue()


def parse_umpp(raw: bytes):
    """Parse a UMPP byte stream; return (headers dict, payload bytes)."""
    assert raw.startswith(PROTOCOL_MAGIC), "Missing MMP/1.0 magic"
    rest = raw[len(PROTOCOL_MAGIC):]
    header_block, _, payload = rest.partition(b"\n\n")
    headers = {}
    for line in header_block.decode('utf-8').splitlines():
        k, _, v = line.partition(':')
        headers[k.strip().lower()] = v.strip()
    return headers, payload


# ---------------------------------------------------------------------------
# emit() / mcat
# ---------------------------------------------------------------------------

class TestEmit(unittest.TestCase):

    def test_magic_header_present(self):
        path = make_temp_image()
        try:
            raw = capture_emit(path)
            self.assertTrue(raw.startswith(PROTOCOL_MAGIC))
        finally:
            os.unlink(path)

    def test_content_type_png(self):
        path = make_temp_image(suffix='.png')
        try:
            headers, _ = parse_umpp(capture_emit(path))
            self.assertEqual(headers['content-type'], 'image/png')
        finally:
            os.unlink(path)

    def test_content_type_jpeg(self):
        path = make_temp_image(suffix='.jpg', data=_JPEG_STUB)
        try:
            headers, _ = parse_umpp(capture_emit(path))
            self.assertIn(headers['content-type'], ('image/jpeg', 'image/jpg'))
        finally:
            os.unlink(path)

    def test_content_length_matches_file(self):
        path = make_temp_image()
        try:
            headers, payload = parse_umpp(capture_emit(path))
            self.assertEqual(int(headers['content-length']), len(_PNG_1x1))
            self.assertEqual(len(payload), len(_PNG_1x1))
        finally:
            os.unlink(path)

    def test_payload_is_exact_binary(self):
        path = make_temp_image()
        try:
            _, payload = parse_umpp(capture_emit(path))
            self.assertEqual(payload, _PNG_1x1)
        finally:
            os.unlink(path)

    def test_missing_file_exits(self):
        buf = io.BytesIO()
        with patch('sys.stdout') as mock_stdout, \
             patch('sys.stderr') as mock_stderr:
            mock_stdout.buffer = buf
            mock_stderr.write = lambda *a, **kw: None
            from mm import emit
            with self.assertRaises(SystemExit) as ctx:
                emit('/tmp/does_not_exist_mmpipe_test.png')
        self.assertEqual(ctx.exception.code, 1)

    def test_unknown_mime_falls_back_to_octet_stream(self):
        path = make_temp_image(suffix='.mmpunknown', data=b'\x00\x01\x02\x03')
        try:
            headers, _ = parse_umpp(capture_emit(path))
            self.assertEqual(headers['content-type'], 'application/octet-stream')
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# analyze_vision() — UMPP protocol path
# ---------------------------------------------------------------------------

def make_umpp_stream(data: bytes, mime: str) -> io.BytesIO:
    """Build a valid UMPP byte stream for feeding into stdin."""
    buf = io.BytesIO()
    buf.write(PROTOCOL_MAGIC)
    buf.write(f"Content-Type: {mime}\n".encode())
    buf.write(f"Content-Length: {len(data)}\n".encode())
    buf.write(b"\n")
    buf.write(data)
    buf.seek(0)
    return buf


class TestAnalyzeVisionUMPP(unittest.TestCase):

    def _run_mock(self, stream: io.BytesIO, prompt="Describe this."):
        """Run analyze_vision with no API key (mock mode) and capture stdout."""
        out = io.StringIO()
        with patch('sys.stdin') as mock_stdin, \
             patch('sys.stdout', new=out), \
             patch.dict(os.environ, {}, clear=False):
            os.environ.pop('GEMINI_API_KEY', None)
            mock_stdin.isatty.return_value = False
            mock_stdin.buffer = stream
            from mm import analyze_vision
            analyze_vision(prompt)
        return out.getvalue()

    def test_mock_output_printed(self):
        stream = make_umpp_stream(_PNG_1x1, 'image/png')
        output = self._run_mock(stream)
        self.assertIn('Mock AI Output', output)

    def test_mock_reports_byte_count(self):
        stream = make_umpp_stream(_PNG_1x1, 'image/png')
        output = self._run_mock(stream)
        self.assertIn(str(len(_PNG_1x1)), output)

    def test_non_image_mime_exits(self):
        data = b'Hello, world'
        stream = make_umpp_stream(data, 'text/plain')
        err = io.StringIO()
        with patch('sys.stdin') as mock_stdin, \
             patch('sys.stderr', new=err), \
             patch.dict(os.environ, {}, clear=False):
            os.environ.pop('GEMINI_API_KEY', None)
            mock_stdin.isatty.return_value = False
            mock_stdin.buffer = stream
            from mm import analyze_vision
            with self.assertRaises(SystemExit) as ctx:
                analyze_vision("describe")
        self.assertEqual(ctx.exception.code, 1)


# ---------------------------------------------------------------------------
# analyze_vision() — magic-byte fallback (plain cat path)
# ---------------------------------------------------------------------------

class TestAnalyzeVisionFallback(unittest.TestCase):

    def _run_mock_raw(self, data: bytes):
        out = io.StringIO()
        with patch('sys.stdin') as mock_stdin, \
             patch('sys.stdout', new=out), \
             patch.dict(os.environ, {}, clear=False):
            os.environ.pop('GEMINI_API_KEY', None)
            mock_stdin.isatty.return_value = False
            mock_stdin.buffer = io.BytesIO(data)
            from mm import analyze_vision
            analyze_vision("describe")
        return out.getvalue()

    def test_jpeg_magic_bytes_detected(self):
        output = self._run_mock_raw(_JPEG_STUB)
        self.assertIn('Mock AI Output', output)

    def test_png_magic_bytes_detected(self):
        output = self._run_mock_raw(_PNG_1x1)
        self.assertIn('Mock AI Output', output)

    def test_unknown_binary_exits(self):
        err = io.StringIO()
        with patch('sys.stdin') as mock_stdin, \
             patch('sys.stderr', new=err), \
             patch.dict(os.environ, {}, clear=False):
            os.environ.pop('GEMINI_API_KEY', None)
            mock_stdin.isatty.return_value = False
            mock_stdin.buffer = io.BytesIO(b'\x00\x01\x02\x03unknown')
            from mm import analyze_vision
            with self.assertRaises(SystemExit) as ctx:
                analyze_vision("describe")
        self.assertEqual(ctx.exception.code, 1)


# ---------------------------------------------------------------------------
# analyze_vision() — live Gemini API path (mocked urllib)
# ---------------------------------------------------------------------------

class TestAnalyzeVisionAPI(unittest.TestCase):

    def test_gemini_response_printed(self):
        fake_response = {
            "candidates": [{
                "content": {"parts": [{"text": "A red circle on white."}]}
            }]
        }
        stream = make_umpp_stream(_PNG_1x1, 'image/png')
        out = io.StringIO()

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(fake_response).encode()
        mock_resp.__enter__ = lambda s, *a: mock_resp
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch('sys.stdin') as mock_stdin, \
             patch('sys.stdout', new=out), \
             patch('urllib.request.urlopen', return_value=mock_resp), \
             patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'}):
            mock_stdin.isatty.return_value = False
            mock_stdin.buffer = stream
            from mm import analyze_vision
            analyze_vision("What is this?")

        self.assertEqual(out.getvalue().strip(), "A red circle on white.")

    def test_api_error_exits(self):
        import urllib.error
        stream = make_umpp_stream(_PNG_1x1, 'image/png')
        err = io.StringIO()

        with patch('sys.stdin') as mock_stdin, \
             patch('sys.stderr', new=err), \
             patch('urllib.request.urlopen', side_effect=Exception("timeout")), \
             patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'}):
            mock_stdin.isatty.return_value = False
            mock_stdin.buffer = stream
            from mm import analyze_vision
            with self.assertRaises(SystemExit) as ctx:
                analyze_vision("describe")
        self.assertEqual(ctx.exception.code, 1)


# ---------------------------------------------------------------------------
# CLI argument routing
# ---------------------------------------------------------------------------

class TestCLI(unittest.TestCase):

    def test_mcat_command_calls_emit(self):
        path = make_temp_image()
        try:
            with patch('mm.emit') as mock_emit:
                with patch('sys.argv', ['mm.py', 'mcat', path]):
                    import mm
                    mm.main()
                mock_emit.assert_called_once_with(path)
        finally:
            os.unlink(path)

    def test_analyze_vision_command_calls_analyze(self):
        with patch('mm.analyze_vision') as mock_av:
            with patch('sys.argv', ['mm.py', 'analyze_vision', 'What is this?']):
                import mm
                mm.main()
            mock_av.assert_called_once_with('What is this?')

    def test_analyze_vision_default_prompt(self):
        with patch('mm.analyze_vision') as mock_av:
            with patch('sys.argv', ['mm.py', 'analyze_vision']):
                import mm
                mm.main()
            mock_av.assert_called_once_with('Describe everything in this image.')

    def test_no_command_exits(self):
        with patch('sys.argv', ['mm.py']):
            with self.assertRaises(SystemExit):
                import mm
                mm.main()


if __name__ == '__main__':
    unittest.main(verbosity=2)
