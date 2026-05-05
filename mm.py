#!/usr/bin/env python3
"""
Multimodal Unix Fix
Implements the Universal Media Pipe Protocol (UMPP) for binary-aware stdin/stdout.
"""

import sys
import os
import mimetypes
import argparse
import urllib.request
import json
import base64

# The Protocol Signature
PROTOCOL_MAGIC = b"MMP/1.0\n"

def emit(file_path):
    """
    Step 01: Universal Media Pipe Protocol (mcat)
    Injects MIME-type metadata alongside the binary payload into stdout's buffer.
    Programs no longer have to 'guess' if incoming data is UTF-8 or a JPEG.
    """
    if not os.path.exists(file_path):
        sys.stderr.write(f"Error: File {file_path} not found.\n")
        sys.exit(1)

    mime_type, _ = mimetypes.guess_type(file_path)
    mime_type = mime_type or 'application/octet-stream'
    size = os.path.getsize(file_path)

    # 1. Write structured protocol headers
    sys.stdout.buffer.write(PROTOCOL_MAGIC)
    sys.stdout.buffer.write(f"Content-Type: {mime_type}\n".encode('utf-8'))
    sys.stdout.buffer.write(f"Content-Length: {size}\n".encode('utf-8'))
    sys.stdout.buffer.write(b"\n")  # Blank line dictates end of headers

    # 2. Safely stream raw binary payload directly to the pipe
    with open(file_path, 'rb') as f:
        while chunk := f.read(8192):
            sys.stdout.buffer.write(chunk)
    sys.stdout.buffer.flush()


def analyze_vision(prompt):
    """
    Step 03: Native Multimodal Scripting (analyze_vision)
    Intercepts the stream, reads metadata, native-reasons across the payload,
    and returns POSIX-compliant text.
    """
    if sys.stdin.isatty():
        sys.stderr.write("Error: Expected piped data (e.g., mcat image.png | analyze_vision).\n")
        sys.exit(1)

    first_line = sys.stdin.buffer.readline()
    mime_type = None
    data = b""

    # Check if the stream uses the Universal Media Pipe Protocol
    if first_line == PROTOCOL_MAGIC:
        headers = {}
        while True:
            line = sys.stdin.buffer.readline()
            if line == b"\n":
                break
            key, val = line.decode('utf-8').split(':', 1)
            headers[key.strip().lower()] = val.strip()

        mime_type = headers.get('content-type', 'application/octet-stream')
        length = int(headers.get('content-length', 0))
        data = sys.stdin.buffer.read(length)
    else:
        # Fallback gracefully if standard 'cat' was used instead of 'mcat'
        data = first_line + sys.stdin.buffer.read()
        # Fallback Magic Byte Sniffing
        if data.startswith(b'\xff\xd8\xff'):
            mime_type = 'image/jpeg'
        elif data.startswith(b'\x89PNG\r\n\x1a\n'):
            mime_type = 'image/png'
        elif data.startswith(b'GIF87a') or data.startswith(b'GIF89a'):
            mime_type = 'image/gif'
        elif data.startswith(b'RIFF') and data[8:12] == b'WEBP':
            mime_type = 'image/webp'
        else:
            mime_type = 'application/octet-stream'

    if not mime_type.startswith('image/'):
        sys.stderr.write(f"Error: Expected an image, got {mime_type}\n")
        sys.exit(1)

    # --- Frontier AI Reasoning Injection ---
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print(f"--- Mock AI Output ---")
        print(f"Analyzed {len(data)} bytes of {mime_type}.")
        print(f"Result: The image contains a sleek terminal interface with a red notification dot.")
        print("(Note: Set GEMINI_API_KEY environment variable for real AI processing)")
        return

    # Native integration with Gemini via REST (zero heavy dependencies)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(data).decode('utf-8')}}
            ]
        }]
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            text_output = result['candidates'][0]['content']['parts'][0]['text'].strip()
            # Output pure UTF-8 text so downstream legacy tools (grep, awk, sed) can filter it
            print(text_output)
    except Exception as e:
        sys.stderr.write(f"API Error: {e}\n")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Multimodal Unix Utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    mcat_parser = subparsers.add_parser("mcat", help="Pipe media with Protocol Headers")
    mcat_parser.add_argument("file", help="Media file to pipe")

    vision_parser = subparsers.add_parser("analyze_vision", help="Analyze incoming media pipe")
    vision_parser.add_argument(
        "prompt",
        nargs="?",
        default="Describe everything in this image.",
        help="Prompt for AI"
    )

    args = parser.parse_args()

    if args.command == "mcat":
        emit(args.file)
    elif args.command == "analyze_vision":
        analyze_vision(args.prompt)


if __name__ == "__main__":
    main()
