from email import policy
from email.parser import BytesParser


class MultipartParseError(Exception):
    pass


def parse_multipart(content_type: str, body: bytes) -> dict[str, bytes]:
    if "multipart/form-data" not in content_type:
        raise MultipartParseError("Expected multipart/form-data.")

    message = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: "
        + content_type.encode("utf-8")
        + b"\r\nMIME-Version: 1.0\r\n\r\n"
        + body
    )
    if not message.is_multipart():
        raise MultipartParseError("Invalid multipart body.")

    parts: dict[str, bytes] = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if name is None:
            continue
        payload = part.get_payload(decode=True)
        parts[name] = payload or b""

    return parts
