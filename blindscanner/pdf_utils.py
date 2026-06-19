from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path


class PDFError(RuntimeError):
    pass


@dataclass(slots=True)
class JPEGInfo:
    width: int
    height: int
    bits_per_component: int
    color_components: int


def read_jpeg_info(path: Path) -> JPEGInfo:
    data = path.read_bytes()
    if len(data) < 4 or data[0:2] != b"\xff\xd8":
        raise PDFError(f"Unsupported JPEG file: {path.name}")

    index = 2
    while index < len(data):
        while index < len(data) and data[index] != 0xFF:
            index += 1
        while index < len(data) and data[index] == 0xFF:
            index += 1
        if index >= len(data):
            break

        marker = data[index]
        index += 1

        if marker in {0xD8, 0xD9, 0x01} or 0xD0 <= marker <= 0xD7:
            continue
        if index + 2 > len(data):
            break

        segment_length = struct.unpack(">H", data[index:index + 2])[0]
        segment_start = index + 2
        segment_end = index + segment_length
        if segment_end > len(data):
            break

        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if segment_length < 8:
                break
            bits = data[segment_start]
            height = struct.unpack(">H", data[segment_start + 1:segment_start + 3])[0]
            width = struct.unpack(">H", data[segment_start + 3:segment_start + 5])[0]
            components = data[segment_start + 5]
            return JPEGInfo(width=width, height=height, bits_per_component=bits, color_components=components)

        index = segment_end

    raise PDFError(f"Failed to read JPEG dimensions: {path.name}")


def _build_pdf_from_jpegs(image_paths: list[Path]) -> bytes:
    if not image_paths:
        raise PDFError("No JPEG images provided")

    objects: list[bytes] = []
    page_refs: list[int] = []
    pages_object_number = 2
    next_object_number = 3

    for image_path in image_paths:
        info = read_jpeg_info(image_path)
        image_bytes = image_path.read_bytes()
        image_object_number = next_object_number
        content_object_number = next_object_number + 1
        page_object_number = next_object_number + 2
        next_object_number += 3

        color_space = b"/DeviceGray" if info.color_components == 1 else b"/DeviceRGB"
        image_dict = (
            f"<< /Type /XObject /Subtype /Image /Width {info.width} /Height {info.height} "
            f"/ColorSpace {color_space.decode('ascii')} /BitsPerComponent {info.bits_per_component} "
            f"/Filter /DCTDecode /Length {len(image_bytes)} >>\n"
        ).encode("ascii")
        objects.append(image_dict + b"stream\n" + image_bytes + b"\nendstream")

        content_stream = (
            f"q\n{info.width} 0 0 {info.height} 0 0 cm\n/Im{image_object_number} Do\nQ\n"
        ).encode("ascii")
        content_dict = f"<< /Length {len(content_stream)} >>\n".encode("ascii")
        objects.append(content_dict + b"stream\n" + content_stream + b"endstream")

        page_dict = (
            f"<< /Type /Page /Parent {pages_object_number} 0 R /MediaBox [0 0 {info.width} {info.height}] "
            f"/Resources << /XObject << /Im{image_object_number} {image_object_number} 0 R >> >> "
            f"/Contents {content_object_number} 0 R >>"
        ).encode("ascii")
        objects.append(page_dict)
        page_refs.append(page_object_number)

    catalog = b"<< /Type /Catalog /Pages 2 0 R >>"
    pages = f"<< /Type /Pages /Count {len(page_refs)} /Kids [{' '.join(f'{ref} 0 R' for ref in page_refs)}] >>".encode("ascii")

    ordered_objects: list[bytes] = [catalog, pages, *objects]

    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_number, body in enumerate(ordered_objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{object_number} 0 obj\n".encode("ascii"))
        pdf.extend(body)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(ordered_objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer\n<< /Size {len(ordered_objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(pdf)


def save_pdf_from_jpegs(image_paths: list[Path], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_bytes = _build_pdf_from_jpegs(image_paths)
    output_path.write_bytes(pdf_bytes)
    return output_path
